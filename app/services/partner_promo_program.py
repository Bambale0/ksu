from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartnerPromoProgramConfig


class PartnerPromoProgramService:
    """Database-owned economics for partner promo attribution."""

    KEY = "default"

    @classmethod
    async def get_config(
        cls,
        session: AsyncSession,
        *,
        for_update: bool = False,
    ) -> PartnerPromoProgramConfig:
        stmt = select(PartnerPromoProgramConfig).where(
            PartnerPromoProgramConfig.key == cls.KEY
        )
        if for_update:
            stmt = stmt.with_for_update()
        config = await session.scalar(stmt)
        if config is None:
            raise RuntimeError("Partner promo program configuration is missing")
        return config

    @staticmethod
    def validate_values(
        *,
        welcome_rox: Decimal,
        first_line_percent: Decimal,
        topup_partner_rox: Decimal,
        payment_bonus_rox: Decimal,
        payment_bonus_min_rub: Decimal,
    ) -> None:
        if welcome_rox != Decimal("0"):
            raise ValueError("Welcome ROX is deprecated and must remain 0")
        if first_line_percent < 0 or first_line_percent > Decimal("100"):
            raise ValueError("First-line percent must be between 0 and 100")
        if topup_partner_rox < 0 or topup_partner_rox > Decimal("100000"):
            raise ValueError("Partner top-up ROX must be between 0 and 100000")
        if payment_bonus_rox < 0 or payment_bonus_rox > Decimal("100000"):
            raise ValueError("Payment bonus ROX must be between 0 and 100000")
        if payment_bonus_min_rub < 0 or payment_bonus_min_rub > Decimal("100000000"):
            raise ValueError("Payment bonus minimum RUB must be between 0 and 100000000")

    @staticmethod
    def view(config: PartnerPromoProgramConfig) -> dict[str, object]:
        return {
            "key": config.key,
            "welcome_rox": str(config.welcome_rox),
            "first_line_percent": str(config.first_line_percent),
            "topup_partner_rox": str(config.topup_partner_rox),
            "payment_bonus_rox": str(config.payment_bonus_rox),
            "payment_bonus_min_rub": str(config.payment_bonus_min_rub),
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
        }
