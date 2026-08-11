from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
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
    ) -> Payment:
        if provider not in cls.PROVIDERS:
            raise UnknownPaymentProviderError(provider)
        package = cls.package(package_id)

        payment = Payment(
            user_id=user_id,
            provider=provider,
            amount=package.amount,
            currency=package.currency,
            rox_amount=package.rox_amount,
            status="creating",
            payload={
                "package_id": package_id,
                "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
            },
        )
        session.add(payment)
        await session.flush()

        description = f"Internal credits: {package.credits}"
        try:
            created = await cls._create_external(
                provider,
                local_id=str(payment.id),
                package=package,
                description=description,
            )
        except Exception as exc:
            payment.status = "failed"
            payment.payload = {**payment.payload, "create_error": str(exc)}
            await session.commit()
            raise

        payment.external_id = created.external_id
        payment.status = "pending"
        payment.payload = {
            **payment.payload,
            "payment_url": created.payment_url,
            "provider_response": created.raw,
        }
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
        if payment.status == "succeeded":
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
        payment.payload = {**payment.payload, "last_webhook": provider_payload}
        await session.commit()
        return payment

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
        if payment.status != "succeeded":
            payment.status = status
            payment.payload = {**payment.payload, "last_webhook": provider_payload}
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
