import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromoCode, PromoRedemption
from app.services.wallet import WalletService


class PromoCodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PromoCodeService:
    @staticmethod
    async def redeem(session: AsyncSession, *, user_id: uuid.UUID, code: str) -> PromoCode:
        promo = await session.scalar(
            select(PromoCode).where(PromoCode.code == code.strip().upper()).with_for_update()
        )
        if promo is None or not promo.is_active:
            raise PromoCodeError("invalid", "Promo code is invalid")
        if promo.expires_at and promo.expires_at <= datetime.now(UTC):
            raise PromoCodeError("expired", "Promo code has expired")
        if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
            raise PromoCodeError("usage_limit_reached", "Promo code usage limit reached")

        used = await session.scalar(
            select(PromoRedemption.id).where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
        if used is not None:
            raise PromoCodeError("already_used", "Promo code already used")

        session.add(PromoRedemption(promo_id=promo.id, user_id=user_id))
        promo.uses_count += 1
        await WalletService.credit(
            session,
            user_id=user_id,
            amount=promo.reward_amount,
            kind="promo_bonus",
            reference_type="promo_code",
            reference_id=str(promo.id),
            idempotency_key=f"promo:{promo.id}:{user_id}",
        )
        return promo
