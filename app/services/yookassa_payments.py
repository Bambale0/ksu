from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.payments import PaymentPackage, PaymentService


class YooKassaPaymentService(PaymentService):
    """YooKassa checkout. Promotional ROX require a payment-bound promo code."""

    PROVIDER = "yookassa"

    @classmethod
    def packages(cls) -> dict[str, PaymentPackage]:
        return PaymentService.packages()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        package_id: str,
        request_key: str,
        promo_code: str | None = None,
    ) -> Payment:
        return await super().create(
            session,
            user_id=user_id,
            provider=cls.PROVIDER,
            package_id=package_id,
            request_key=request_key,
            promo_code=promo_code,
        )
