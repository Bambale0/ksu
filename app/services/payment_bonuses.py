from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.wallet import WalletService


class TopUpBonusService:
    """Apply the configured package gift as a separate wallet transaction."""

    @staticmethod
    def package_bonus(payload: dict[str, object] | None) -> Decimal:
        return Decimal(str((payload or {}).get("package_bonus_credits") or "0"))

    @staticmethod
    def total_for(*, base: Decimal, package_bonus: Decimal, promo_bonus: Decimal = Decimal("0")) -> Decimal:
        return Decimal(base) + Decimal(package_bonus) + Decimal(promo_bonus)

    @classmethod
    async def apply_package_bonus(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
    ) -> Decimal:
        payload = payment.payload or {}
        bonus = cls.package_bonus(payload)
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        promo_bonus = Decimal(str(payload.get("promo_bonus_credits") or "0"))
        if bonus > 0:
            await WalletService.credit(
                session,
                user_id=payment.user_id,
                amount=bonus,
                kind="topup_package_bonus",
                reference_type="payment",
                reference_id=str(payment.id),
                idempotency_key=f"payment:{payment.id}:package-bonus",
                reason="package_topup_bonus",
                payment_id=payment.id,
            )
        payment.payload = {
            **payload,
            "package_bonus_status": "applied" if bonus > 0 else "none",
            "package_bonus_credits": str(bonus),
            "bonus_credits": str(bonus + promo_bonus),
            "credited_credits": str(base + bonus + promo_bonus),
        }
        return bonus
