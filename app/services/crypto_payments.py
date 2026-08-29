from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.providers.payments import CryptoPayClient, PaymentProviderError
from app.services.card_payments import CardPackage, CardPackageCatalog
from app.services.credits import InternalCreditService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payments import PaymentIdempotencyConflict, UnknownPaymentPackageError


class CryptoBotPaymentService:
    PROVIDER = "cryptobot"
    PUBLIC_LABEL = "CryptoBot"
    CURRENCY = "RUB"

    @staticmethod
    def provider_configured() -> bool:
        return bool(settings.cryptopay_api_token)

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
            raise PaymentProviderError("CryptoBot is not configured")
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
            # Persist the local intent before createInvoice. Crypto Pay has no
            # create-invoice idempotency key, so reconciliation uses payload=payment.id.
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

        client = CryptoPayClient(settings.cryptopay_api_token, settings.cryptopay_base_url)
        try:
            created = await client.create_payment(
                local_id=str(payment.id),
                amount=amount,
                currency=cls.CURRENCY,
                description=f"Пополнение ROXY: {base_credits} ROX",
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
            raise LookupError("Payment disappeared after Crypto Pay invoice creation")
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
        await session.refresh(payment)
        return payment
