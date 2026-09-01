from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.payment_bonuses import TopUpBonusService
from app.services.payments import PaymentPackage, PaymentService


class YooKassaPaymentService(PaymentService):
    """YooKassa checkout with operator-owned ROX package bonuses."""

    PROVIDER = "yookassa"

    @classmethod
    def packages(cls) -> dict[str, PaymentPackage]:
        result: dict[str, PaymentPackage] = {}
        for package_id, package in PaymentService.packages().items():
            result[package_id] = PaymentPackage(
                package_id=package.package_id,
                amount=package.amount,
                currency=package.currency,
                rox_amount=TopUpBonusService.total_for(package.credits),
            )
        return result

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        package_id: str,
        request_key: str,
    ) -> Payment:
        base_package = PaymentService.package(package_id)
        payment = await super().create(
            session,
            user_id=user_id,
            provider=cls.PROVIDER,
            package_id=package_id,
            request_key=request_key,
        )

        base_credits = Decimal(base_package.credits)
        credited_credits = Decimal(payment.rox_amount)
        bonus_credits = max(Decimal("0"), credited_credits - base_credits)
        payment.payload = {
            **(payment.payload or {}),
            "base_credits": str(base_credits),
            "bonus_credits": str(bonus_credits),
            "credited_credits": str(credited_credits),
        }
        await session.commit()
        await session.refresh(payment)
        return payment
