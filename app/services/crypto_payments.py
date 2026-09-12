from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.providers.payments import CryptoPayClient, PaymentProviderError
from app.services.card_payments import CardPackage, CardPackageCatalog
from app.services.credits import InternalCreditService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payment_creation import PaymentCreationLifecycle
from app.services.payments import UnknownPaymentPackageError


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

        package = await cls.provider_package(package_id)
        amount = package.prices.get(cls.CURRENCY)
        if amount is None:
            raise UnknownPaymentPackageError(package_id)

        base_credits = Decimal(package.credits)
        bonus_credits = TopUpBonusService.bonus_for(base_credits)
        credited_credits = base_credits + bonus_credits
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
        creation = await PaymentCreationLifecycle.begin(
            session,
            payment=payment,
            user_id=user_id,
            provider=cls.PROVIDER,
            package_id=package_id,
            request_key=request_key,
        )
        if not creation.created:
            return creation.payment
        assert creation.request_id is not None
        payment = creation.payment

        client = CryptoPayClient(settings.cryptopay_api_token, settings.cryptopay_base_url)
        try:
            created = await client.create_payment(
                local_id=str(payment.id),
                amount=amount,
                currency=cls.CURRENCY,
                description=f"Пополнение ROXY: {base_credits} ROX",
            )
        except Exception as exc:
            await PaymentCreationLifecycle.mark_unknown(
                session,
                payment_id=payment.id,
                request_id=creation.request_id,
                error=exc,
            )
            raise
        finally:
            await client.aclose()

        return await PaymentCreationLifecycle.mark_pending(
            session,
            payment_id=payment.id,
            request_id=creation.request_id,
            created=created,
            missing_message="Payment disappeared after Crypto Pay invoice creation",
            refresh=True,
        )

