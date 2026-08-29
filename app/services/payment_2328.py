from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.payment_2328_config import payment_2328_settings
from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.providers.payment_2328 import (
    FINAL_FAILURE_STATUSES,
    PENDING_STATUSES,
    SUCCESS_STATUSES,
    Payment2328Client,
)
from app.providers.payments import PaymentProviderError
from app.services.card_payments import CardPackage, CardPackageCatalog
from app.services.credits import InternalCreditService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payments import (
    PaymentIdempotencyConflict,
    PaymentService,
    UnknownPaymentPackageError,
)


class Payment2328Service:
    PROVIDER = "2328"
    PUBLIC_LABEL = "Криптовалюта"
    CURRENCY = "RUB"

    @staticmethod
    def provider_configured() -> bool:
        return bool(payment_2328_settings.project_uuid and payment_2328_settings.api_key)

    @classmethod
    async def provider_packages(cls) -> dict[str, CardPackage]:
        packages = await CardPackageCatalog.provider_packages()
        return {
            package_id: package
            for package_id, package in packages.items()
            if cls.CURRENCY in package.prices
        }

    @classmethod
    async def provider_package(cls, package_id: str) -> CardPackage:
        package = (await cls.provider_packages()).get(package_id)
        if package is None:
            raise UnknownPaymentPackageError(package_id)
        return package

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        package_id: str,
        request_key: str,
    ) -> Payment:
        if not cls.provider_configured():
            raise PaymentProviderError("2328.io is not configured")
        if not request_key or len(request_key) > 64:
            raise ValueError("Idempotency key must contain 1-64 characters")

        package = await cls.provider_package(package_id)
        amount = package.prices.get(cls.CURRENCY)
        if amount is None:
            raise UnknownPaymentPackageError(package_id)

        base_credits = Decimal(package.credits)
        bonus_credits = TopUpBonusService.bonus_for(base_credits)
        credited_credits = base_credits + bonus_credits

        existing_request = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.user_id == user_id,
                PaymentRequest.request_key == request_key,
            )
        )
        if existing_request is not None:
            existing_payment = await session.get(Payment, existing_request.payment_id)
            if (
                existing_request.provider != cls.PROVIDER
                or existing_request.package_id != package_id
                or existing_payment is None
            ):
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            return existing_payment

        payment = Payment(
            user_id=user_id,
            provider=cls.PROVIDER,
            amount=amount,
            currency=cls.CURRENCY,
            rox_amount=credited_credits,
            status="creating",
            payload={
                "package_id": package_id,
                "request_key": request_key,
                "base_credits": str(base_credits),
                "bonus_credits": str(bonus_credits),
                "credited_credits": str(credited_credits),
                "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
            },
        )
        session.add(payment)
        await session.flush()
        request_row = PaymentRequest(
            user_id=user_id,
            payment_id=payment.id,
            request_key=request_key,
            provider=cls.PROVIDER,
            package_id=package_id,
            status="creating",
        )
        session.add(request_row)
        try:
            # 2328.io uses order_id as its creation idempotency key. Persist the
            # local UUID first and use it unchanged for every retry/reconciliation.
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
            existing_payment = await session.get(Payment, winner.payment_id)
            if (
                winner.provider != cls.PROVIDER
                or winner.package_id != package_id
                or existing_payment is None
            ):
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            return existing_payment

        client = cls._client()
        try:
            created = await client.create_payment(
                local_id=str(payment.id),
                amount=amount,
                currency=cls.CURRENCY,
                description=f"Пополнение ROXY: {base_credits} ROX",
                callback_url=settings.webhook_url("webhooks/payments/2328"),
            )
        except Exception as exc:
            payment = await session.get(Payment, payment.id)
            request_row = await session.get(PaymentRequest, request_row.id)
            if payment is not None:
                payment.status = "creation_unknown"
                payment.payload = {**payment.payload, "create_error": str(exc)}
            if request_row is not None:
                request_row.status = "unknown"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise
        finally:
            await client.aclose()

        payment = await session.get(Payment, payment.id)
        request_row = await session.get(PaymentRequest, request_row.id)
        if payment is None or request_row is None:
            raise LookupError("Payment disappeared after 2328.io payment creation")
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

    @classmethod
    async def reconcile(cls, session: AsyncSession, *, payment_id: uuid.UUID) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider is not 2328.io")

        client = cls._client()
        try:
            state = await client.get_payment_info(
                external_id=str(payment.external_id) if payment.external_id else None,
                order_id=None if payment.external_id else str(payment.id),
            )
        finally:
            await client.aclose()
        if state is None:
            return payment
        return await cls.apply_state(session, payment=payment, provider_payload=state)

    @classmethod
    async def apply_state(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        provider_payload: dict[str, Any],
    ) -> Payment:
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider is not 2328.io")
        if str(provider_payload.get("order_id") or "") != str(payment.id):
            raise PaymentProviderError("2328.io order_id mismatch")

        external_id = str(provider_payload.get("uuid") or "")
        if not external_id:
            raise PaymentProviderError("2328.io payment UUID is missing")
        if payment.external_id and str(payment.external_id) != external_id:
            raise PaymentProviderError("2328.io payment UUID mismatch")
        if not payment.external_id:
            payment.external_id = external_id

        PaymentService.assert_amount(
            payment,
            amount=Decimal(str(provider_payload.get("amount") or "0")),
            currency=str(provider_payload.get("currency") or ""),
        )
        provider_status = str(provider_payload.get("payment_status") or "").lower()
        request_row = await session.scalar(
            select(PaymentRequest).where(PaymentRequest.payment_id == payment.id)
        )
        if request_row is not None and request_row.status == "unknown":
            request_row.status = "completed"
            request_row.last_error = None

        if provider_status in SUCCESS_STATUSES:
            return await PaymentService.complete(
                session,
                payment_id=payment.id,
                provider_payload=provider_payload,
            )

        if payment.status not in PaymentService.TERMINAL_STATUSES:
            if provider_status == "cancel":
                payment.status = "expired"
            elif provider_status in {"underpaid", "aml_lock"}:
                payment.status = "failed"
            elif provider_status in PENDING_STATUSES or not provider_status:
                payment.status = "pending"
            elif provider_status in FINAL_FAILURE_STATUSES:
                payment.status = "failed"
            else:
                raise PaymentProviderError(f"Unknown 2328.io payment status: {provider_status}")
            payment.payload = {
                **(payment.payload or {}),
                "last_provider_state": provider_payload,
            }
            await session.commit()
        return payment

    @staticmethod
    def _client() -> Payment2328Client:
        return Payment2328Client(
            payment_2328_settings.project_uuid,
            payment_2328_settings.api_key,
            payment_2328_settings.base_url,
        )
