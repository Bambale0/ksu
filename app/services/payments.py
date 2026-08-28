from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment, WalletTransaction
from app.db.payment_models import PaymentRefundRequest, PaymentRequest, PaymentReversal
from app.providers.payments import (
    CreatedPayment,
    CryptoPayClient,
    PaymentProviderError,
    TBankClient,
    YooKassaClient,
)
from app.services.credits import InternalCreditService
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


class UnknownPaymentPackageError(ValueError):
    pass


class UnknownPaymentProviderError(ValueError):
    pass


class PaymentIdempotencyConflict(ValueError):
    pass


class UnsupportedPaymentOperation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PaymentPackage:
    package_id: str
    amount: Decimal
    currency: str
    rox_amount: Decimal

    @property
    def credits(self) -> Decimal:
        return self.rox_amount


class PaymentService:
    PROVIDERS = {"cryptobot", "tbank", "yookassa"}
    TERMINAL_STATUSES = {"succeeded", "failed", "canceled", "expired", "refunded"}

    @staticmethod
    def provider_configured(provider: str) -> bool:
        if provider == "cryptobot":
            return bool(settings.cryptopay_api_token)
        if provider == "tbank":
            return bool(settings.tbank_terminal_key and settings.tbank_password)
        if provider == "yookassa":
            return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)
        return False

    @staticmethod
    def packages() -> dict[str, PaymentPackage]:
        try:
            raw = json.loads(settings.rox_packages_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("ROX_PACKAGES_JSON is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("ROX_PACKAGES_JSON must be a JSON object")

        result: dict[str, PaymentPackage] = {}
        for package_id, item in raw.items():
            if not isinstance(item, dict):
                continue

            currency = str(item.get("currency", "RUB")).upper()
            if currency != "RUB":
                raise ValueError(
                    f"Package {package_id} must use RUB because internal credits have a fixed RUB rate"
                )

            amount_raw = item.get("amount")
            credits_raw = item.get("credits", item.get("rox"))
            if amount_raw is None and credits_raw is None:
                continue

            amount = Decimal(str(amount_raw)) if amount_raw is not None else None
            credits = Decimal(str(credits_raw)) if credits_raw is not None else None

            if amount is None and credits is not None:
                amount = InternalCreditService.rubles_for(credits)
            elif credits is None and amount is not None:
                credits = InternalCreditService.credits_for(amount)

            assert amount is not None and credits is not None
            if amount <= 0 or credits <= 0:
                continue

            InternalCreditService.assert_rate(credits=credits, rubles=amount)
            result[str(package_id)] = PaymentPackage(
                package_id=str(package_id),
                amount=amount,
                currency=currency,
                rox_amount=credits,
            )
        return result

    @classmethod
    def package(cls, package_id: str) -> PaymentPackage:
        package = cls.packages().get(package_id)
        if package is None:
            raise UnknownPaymentPackageError(package_id)
        return package

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        provider: str,
        package_id: str,
        request_key: str,
    ) -> Payment:
        if provider not in cls.PROVIDERS:
            raise UnknownPaymentProviderError(provider)
        if not request_key or len(request_key) > 64:
            raise ValueError("Idempotency key must contain 1-64 characters")
        package = cls.package(package_id)

        existing_request = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.user_id == user_id,
                PaymentRequest.request_key == request_key,
            )
        )
        if existing_request is not None:
            if existing_request.provider != provider or existing_request.package_id != package_id:
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            existing_payment = await session.get(Payment, existing_request.payment_id)
            if existing_payment is None:
                raise LookupError("Idempotent payment record is inconsistent")
            return existing_payment

        payment = Payment(
            user_id=user_id,
            provider=provider,
            amount=package.amount,
            currency=package.currency,
            rox_amount=package.rox_amount,
            status="creating",
            payload={
                "package_id": package_id,
                "request_key": request_key,
                "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
            },
        )
        session.add(payment)
        await session.flush()
        payment_request = PaymentRequest(
            user_id=user_id,
            payment_id=payment.id,
            request_key=request_key,
            provider=provider,
            package_id=package_id,
            status="creating",
        )
        session.add(payment_request)
        try:
            # The local intent becomes durable before the external side effect.
            await session.commit()
        except IntegrityError:
            await session.rollback()
            winner = await session.scalar(
                select(PaymentRequest).where(
                    PaymentRequest.user_id == user_id,
                    PaymentRequest.request_key == request_key,
                )
            )
            if winner is None:
                raise
            if winner.provider != provider or winner.package_id != package_id:
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            existing_payment = await session.get(Payment, winner.payment_id)
            if existing_payment is None:
                raise LookupError("Idempotent payment record is inconsistent")
            return existing_payment

        description = f"Internal credits: {package.credits}"
        try:
            created = await cls._create_external(
                provider,
                local_id=str(payment.id),
                package=package,
                description=description,
            )
        except Exception as exc:
            payment = await session.get(Payment, payment.id)
            request_row = await session.get(PaymentRequest, payment_request.id)
            if payment is not None:
                payment.status = "creation_unknown"
                payment.payload = {**payment.payload, "create_error": str(exc)}
            if request_row is not None:
                request_row.status = "unknown"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise

        payment = await session.get(Payment, payment.id)
        request_row = await session.get(PaymentRequest, payment_request.id)
        if payment is None or request_row is None:
            raise LookupError("Payment disappeared after provider creation")
        payment.external_id = created.external_id
        payment.status = "pending"
        payment.payload = {
            **payment.payload,
            "payment_url": created.payment_url,
            "provider_response": created.raw,
        }
        request_row.status = "completed"
        request_row.last_error = None
        await session.commit()
        return payment

    @staticmethod
    async def _create_external(
        provider: str,
        *,
        local_id: str,
        package: PaymentPackage,
        description: str,
    ) -> CreatedPayment:
        if provider == "cryptobot":
            client = CryptoPayClient(settings.cryptopay_api_token, settings.cryptopay_base_url)
            try:
                return await client.create_payment(
                    local_id=local_id,
                    amount=package.amount,
                    currency=package.currency,
                    description=description,
                )
            finally:
                await client.aclose()

        if provider == "tbank":
            client = TBankClient(
                settings.tbank_terminal_key,
                settings.tbank_password,
                settings.tbank_base_url,
            )
            try:
                return await client.create_payment(
                    local_id=local_id,
                    amount=package.amount,
                    description=description,
                    notification_url=settings.webhook_url("webhooks/payments/tbank"),
                    return_url=settings.payment_return_url or settings.public_base_url,
                )
            finally:
                await client.aclose()

        if provider == "yookassa":
            return_url = settings.payment_return_url or settings.public_base_url
            if not return_url:
                raise PaymentProviderError(
                    "YooKassa requires PAYMENT_RETURN_URL or PUBLIC_BASE_URL"
                )
            client = YooKassaClient(
                settings.yookassa_shop_id,
                settings.yookassa_secret_key,
                settings.yookassa_base_url,
            )
            try:
                return await client.create_payment(
                    local_id=local_id,
                    amount=package.amount,
                    currency=package.currency,
                    description=description,
                    return_url=return_url,
                )
            finally:
                await client.aclose()

        raise UnknownPaymentProviderError(provider)

    @classmethod
    async def complete(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        provider_payload: dict[str, Any],
    ) -> Payment:
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise LookupError("Payment not found")
        if payment.status in {"succeeded", "partially_refunded", "refunded"}:
            return payment

        wallet_tx = await WalletService.credit(
            session,
            user_id=payment.user_id,
            amount=Decimal(payment.rox_amount),
            kind="payment",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment:{payment.id}:credit",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=payment.user_id,
            source_transaction_id=wallet_tx.id,
            payment_amount=Decimal(payment.amount),
        )
        payment.status = "succeeded"
        payment.payload = {**payment.payload, "last_provider_state": provider_payload}
        await session.commit()
        return payment

    @classmethod
    async def apply_reversal(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        amount: Decimal,
        provider: str,
        idempotency_key: str,
        reason: str,
        provider_payload: dict[str, Any],
        provider_event_id: str | None = None,
    ) -> Payment:
        if amount <= 0:
            raise ValueError("Reversal amount must be positive")
        existing = await session.scalar(
            select(PaymentReversal).where(PaymentReversal.idempotency_key == idempotency_key)
        )
        if existing is not None:
            payment = await session.get(Payment, existing.payment_id)
            if payment is None:
                raise LookupError("Reversed payment no longer exists")
            return payment

        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != provider:
            raise PaymentProviderError("Reversal provider does not match local payment")
        if payment.status not in {"succeeded", "partially_refunded", "refunded"}:
            raise PaymentProviderError("Cannot reverse a payment that was not credited")

        already_amount = await cls.reversed_amount(session, payment.id)
        remaining_amount = Decimal(payment.amount) - already_amount
        if amount > remaining_amount:
            raise PaymentProviderError("Provider reversal exceeds remaining payment amount")

        cumulative_amount = already_amount + amount
        ratio = cumulative_amount / Decimal(payment.amount)
        already_credits = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PaymentReversal.credits), 0)).where(
                        PaymentReversal.payment_id == payment.id
                    )
                )
            )
            or 0
        )
        if cumulative_amount >= Decimal(payment.amount):
            target_credits = Decimal(payment.rox_amount)
        else:
            target_credits = (Decimal(payment.rox_amount) * ratio).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        incremental_credits = max(Decimal("0"), target_credits - already_credits)

        reversal = PaymentReversal(
            payment_id=payment.id,
            provider=provider,
            provider_event_id=provider_event_id,
            idempotency_key=idempotency_key,
            amount=amount,
            credits=incremental_credits,
            reason=reason[:64],
            provider_payload=provider_payload,
        )
        session.add(reversal)
        await session.flush()

        if incremental_credits > 0:
            await WalletService.accounting_debit(
                session,
                user_id=payment.user_id,
                amount=incremental_credits,
                kind="payment_reversal",
                reference_type="payment_reversal",
                reference_id=str(reversal.id),
                idempotency_key=f"payment:{payment.id}:reversal:{reversal.id}",
            )

        source_transaction = await session.scalar(
            select(WalletTransaction).where(
                WalletTransaction.user_id == payment.user_id,
                WalletTransaction.kind == "payment",
                WalletTransaction.reference_type == "payment",
                WalletTransaction.reference_id == str(payment.id),
            )
        )
        if source_transaction is not None:
            await ReferralService.reverse_payment_rewards(
                session,
                source_transaction_id=source_transaction.id,
                payment_reversal_id=reversal.id,
                cumulative_ratio=min(Decimal("1"), ratio),
            )

        payment.status = (
            "refunded" if cumulative_amount >= Decimal(payment.amount) else "partially_refunded"
        )
        payment.payload = {
            **payment.payload,
            "last_reversal": provider_payload,
            "refunded_amount": str(cumulative_amount),
            "refunded_credits": str(target_credits),
        }
        await session.commit()
        return payment

    @staticmethod
    async def reversed_amount(session: AsyncSession, payment_id: uuid.UUID) -> Decimal:
        return Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PaymentReversal.amount), 0)).where(
                        PaymentReversal.payment_id == payment_id
                    )
                )
            )
            or 0
        )

    @classmethod
    async def initiate_refund(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        amount: Decimal,
        request_key: str,
        reason: str,
    ) -> PaymentRefundRequest:
        if amount <= 0:
            raise ValueError("Refund amount must be positive")
        if not request_key or len(request_key) > 64:
            raise ValueError("Refund idempotency key must contain 1-64 characters")

        existing = await session.scalar(
            select(PaymentRefundRequest).where(
                PaymentRefundRequest.payment_id == payment_id,
                PaymentRefundRequest.request_key == request_key,
            )
        )
        if existing is not None:
            if Decimal(existing.amount) != amount:
                raise PaymentIdempotencyConflict(
                    "Refund idempotency key was already used for another amount"
                )
            return existing

        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != "yookassa":
            raise UnsupportedPaymentOperation(
                "Merchant-initiated refunds are currently implemented only for YooKassa"
            )
        if payment.status not in {"succeeded", "partially_refunded"}:
            raise PaymentProviderError("Only a credited payment can be refunded")
        remaining = Decimal(payment.amount) - await cls.reversed_amount(session, payment.id)
        if amount > remaining:
            raise PaymentProviderError("Refund amount exceeds remaining payment amount")
        if not payment.external_id:
            raise PaymentProviderError("Payment has no provider id")

        request_row = PaymentRefundRequest(
            payment_id=payment.id,
            request_key=request_key,
            provider=payment.provider,
            amount=amount,
            currency=payment.currency,
            status="creating",
            reason=reason[:255],
        )
        session.add(request_row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            winner = await session.scalar(
                select(PaymentRefundRequest).where(
                    PaymentRefundRequest.payment_id == payment_id,
                    PaymentRefundRequest.request_key == request_key,
                )
            )
            if winner is None:
                raise
            if Decimal(winner.amount) != amount:
                raise PaymentIdempotencyConflict(
                    "Refund idempotency key was already used for another amount"
                )
            return winner

        client = YooKassaClient(
            settings.yookassa_shop_id,
            settings.yookassa_secret_key,
            settings.yookassa_base_url,
        )
        try:
            provider_refund = await client.create_refund(
                external_payment_id=str(payment.external_id),
                amount=amount,
                currency=payment.currency,
                idempotency_key=request_key,
                description=reason,
            )
        except Exception as exc:
            request_row = await session.get(PaymentRefundRequest, request_row.id)
            if request_row is not None:
                request_row.status = "unknown"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise
        finally:
            await client.aclose()

        request_row = await session.get(PaymentRefundRequest, request_row.id)
        if request_row is None:
            raise LookupError("Refund request disappeared")
        if str(provider_refund.get("payment_id") or "") != str(payment.external_id):
            raise PaymentProviderError("YooKassa refund payment id mismatch")
        refund_amount = provider_refund.get("amount") or {}
        if (
            Decimal(str(refund_amount.get("value") or "0")) != amount
            or str(refund_amount.get("currency") or "").upper() != payment.currency.upper()
        ):
            raise PaymentProviderError("YooKassa refund amount mismatch")

        request_row.provider_refund_id = str(provider_refund.get("id") or "") or None
        request_row.status = str(provider_refund.get("status") or "pending")
        request_row.provider_payload = provider_refund
        request_row.last_error = None
        await session.commit()

        if request_row.status == "succeeded":
            await cls.apply_reversal(
                session,
                payment_id=payment.id,
                amount=amount,
                provider="yookassa",
                idempotency_key=f"yookassa:refund:{request_row.provider_refund_id or request_key}",
                reason="refund",
                provider_payload=provider_refund,
                provider_event_id=request_row.provider_refund_id,
            )
        return request_row

    @classmethod
    async def reconcile(cls, session: AsyncSession, *, payment_id: uuid.UUID) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")

        if payment.provider == "cryptobot":
            client = CryptoPayClient(settings.cryptopay_api_token, settings.cryptopay_base_url)
            try:
                invoice = (
                    await client.get_invoice(str(payment.external_id))
                    if payment.external_id
                    else await client.find_invoice_by_payload(str(payment.id))
                )
            finally:
                await client.aclose()
            if invoice is None:
                return payment
            if str(invoice.get("payload") or "") != str(payment.id):
                raise PaymentProviderError("Crypto Pay invoice payload mismatch")
            external_id = str(invoice.get("invoice_id") or "")
            if external_id and not payment.external_id:
                payment.external_id = external_id
            cls.assert_amount(
                payment,
                amount=Decimal(str(invoice.get("amount") or "0")),
                currency=str(invoice.get("fiat") or payment.currency),
            )
            status = str(invoice.get("status") or "").lower()
            if status == "paid":
                return await cls.complete(session, payment_id=payment.id, provider_payload=invoice)
            if payment.status not in cls.TERMINAL_STATUSES:
                payment.status = "expired" if status == "expired" else "pending"
                payment.payload = {**payment.payload, "last_provider_state": invoice}
                await session.commit()
            return payment

        if payment.provider == "tbank":
            client = TBankClient(
                settings.tbank_terminal_key,
                settings.tbank_password,
                settings.tbank_base_url,
            )
            try:
                if not payment.external_id:
                    order = await client.check_order(str(payment.id))
                    candidate = cls._find_tbank_payment(order)
                    if candidate is None:
                        payment.payload = {**payment.payload, "last_reconcile": order}
                        await session.commit()
                        return payment
                    payment.external_id = str(candidate.get("PaymentId") or "") or None
                    await session.commit()
                if not payment.external_id:
                    return payment
                state = await client.get_state(str(payment.external_id))
            finally:
                await client.aclose()
            return await cls.apply_tbank_state(session, payment.id, state)

        if payment.provider == "yookassa":
            client = YooKassaClient(
                settings.yookassa_shop_id,
                settings.yookassa_secret_key,
                settings.yookassa_base_url,
            )
            try:
                if not payment.external_id:
                    package_id = str((payment.payload or {}).get("package_id") or "")
                    package = cls.package(package_id)
                    created = await client.create_payment(
                        local_id=str(payment.id),
                        amount=package.amount,
                        currency=package.currency,
                        description=f"Internal credits: {package.credits}",
                        return_url=settings.payment_return_url or settings.public_base_url,
                    )
                    payment.external_id = created.external_id
                    payment.payload = {
                        **payment.payload,
                        "payment_url": created.payment_url,
                        "provider_response": created.raw,
                    }
                    await session.commit()
                authoritative = await client.get_payment(str(payment.external_id))
            finally:
                await client.aclose()
            return await cls.apply_yookassa_state(
                session,
                payment.id,
                authoritative,
            )

        raise UnknownPaymentProviderError(payment.provider)

    @classmethod
    async def apply_yookassa_state(
        cls,
        session: AsyncSession,
        payment_id: uuid.UUID,
        authoritative: dict[str, Any],
        *,
        refund_event_id: str | None = None,
    ) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if str(authoritative.get("id") or "") != str(payment.external_id):
            raise PaymentProviderError("YooKassa payment mismatch")
        metadata = authoritative.get("metadata") or {}
        if str(metadata.get("payment_id") or "") != str(payment.id):
            raise PaymentProviderError("YooKassa metadata mismatch")
        amount = authoritative.get("amount") or {}
        cls.assert_amount(
            payment,
            amount=Decimal(str(amount.get("value") or "0")),
            currency=str(amount.get("currency") or ""),
        )

        provider_status = str(authoritative.get("status") or "")
        if provider_status == "succeeded" and payment.status not in {
            "succeeded",
            "partially_refunded",
            "refunded",
        }:
            payment = await cls.complete(
                session,
                payment_id=payment.id,
                provider_payload=authoritative,
            )
        elif provider_status == "canceled" and payment.status not in {
            "succeeded",
            "partially_refunded",
            "refunded",
        }:
            payment.status = "canceled"
            payment.payload = {**payment.payload, "last_provider_state": authoritative}
            await session.commit()
        elif payment.status not in cls.TERMINAL_STATUSES and payment.status != "partially_refunded":
            payment.status = "pending"
            payment.payload = {**payment.payload, "last_provider_state": authoritative}
            await session.commit()

        refunded = authoritative.get("refunded_amount") or {}
        cumulative_refunded = Decimal(str(refunded.get("value") or "0"))
        refunded_currency = str(refunded.get("currency") or payment.currency)
        if refunded_currency.upper() != payment.currency.upper():
            raise PaymentProviderError("YooKassa refunded currency mismatch")
        already_reversed = await cls.reversed_amount(session, payment.id)
        delta = cumulative_refunded - already_reversed
        if delta > 0:
            payment = await cls.apply_reversal(
                session,
                payment_id=payment.id,
                amount=delta,
                provider="yookassa",
                idempotency_key=(
                    f"yookassa:refund:{refund_event_id}"
                    if refund_event_id
                    else f"yookassa:cumulative:{payment.external_id}:{cumulative_refunded}"
                ),
                reason="refund",
                provider_payload=authoritative,
                provider_event_id=refund_event_id,
            )
        return payment

    @classmethod
    async def apply_tbank_state(
        cls,
        session: AsyncSession,
        payment_id: uuid.UUID,
        provider_payload: dict[str, Any],
    ) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        external_id = str(provider_payload.get("PaymentId") or "")
        if external_id and payment.external_id and external_id != str(payment.external_id):
            raise PaymentProviderError("T-Bank payment mismatch")
        if external_id and not payment.external_id:
            payment.external_id = external_id
        if provider_payload.get("Amount") is not None:
            cents = int(provider_payload.get("Amount") or 0)
            expected_cents = int(
                (Decimal(payment.amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if cents != expected_cents:
                raise PaymentProviderError("T-Bank amount mismatch")

        state = str(provider_payload.get("Status") or "").upper()
        if state == "CONFIRMED":
            return await cls.complete(
                session,
                payment_id=payment.id,
                provider_payload=provider_payload,
            )
        if state in {"REFUNDED", "REVERSED"} and payment.status in {
            "succeeded",
            "partially_refunded",
        }:
            already = await cls.reversed_amount(session, payment.id)
            remaining = max(Decimal("0"), Decimal(payment.amount) - already)
            if remaining > 0:
                return await cls.apply_reversal(
                    session,
                    payment_id=payment.id,
                    amount=remaining,
                    provider="tbank",
                    idempotency_key=f"tbank:{payment.external_id}:{state}:full",
                    reason=state.lower(),
                    provider_payload=provider_payload,
                )
            return payment
        if state in {"PARTIAL_REFUNDED", "PARTIAL_REVERSED"}:
            # Do not guess a partial amount from fields whose semantics differ by
            # T-Bank operation/notification. Preserve it for explicit reconciliation.
            payment.status = "refund_review"
        elif state in {"REJECTED", "CANCELED"} and payment.status not in {
            "succeeded",
            "partially_refunded",
            "refunded",
        }:
            payment.status = "canceled"
        elif payment.status not in cls.TERMINAL_STATUSES:
            payment.status = "pending"
        payment.payload = {**payment.payload, "last_provider_state": provider_payload}
        await session.commit()
        return payment

    @staticmethod
    def _find_tbank_payment(payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("PaymentId"):
            return payload
        for key in ("Payments", "payments", "PaymentList", "paymentList"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("PaymentId"):
                        return item
        return None

    @staticmethod
    async def mark_status(
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        status: str,
        provider_payload: dict[str, Any],
    ) -> Payment:
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise LookupError("Payment not found")
        if payment.status not in {"succeeded", "partially_refunded", "refunded"}:
            payment.status = status
            payment.payload = {**payment.payload, "last_provider_state": provider_payload}
            await session.commit()
        return payment

    @staticmethod
    async def get_locked(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
        return await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )

    @staticmethod
    def assert_amount(payment: Payment, *, amount: Decimal, currency: str) -> None:
        if Decimal(payment.amount) != amount or payment.currency.upper() != currency.upper():
            raise PaymentProviderError("Provider payment amount does not match local payment")
