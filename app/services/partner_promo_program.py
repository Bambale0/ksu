from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartnerPromoProgramConfig, PartnerReferralTerms


@dataclass(frozen=True)
class PartnerReferralTermsView:
    first_line_percent: Decimal
    second_line_percent: Decimal


class PartnerPromoProgramService:
    """Database-owned registration welcome and partner-promo economics.

    `welcome_rox` is retained as the compatibility field name, but represents
    the one-time ROX grant issued when a user account is first registered.
    """

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

    @classmethod
    async def referral_terms(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> PartnerReferralTermsView:
        terms = await session.get(PartnerReferralTerms, user_id)
        if terms is not None:
            return PartnerReferralTermsView(
                first_line_percent=Decimal(terms.first_line_percent),
                second_line_percent=Decimal(terms.second_line_percent),
            )
        config = await cls.get_config(session)
        return PartnerReferralTermsView(
            first_line_percent=Decimal(config.first_line_percent),
            second_line_percent=Decimal("0"),
        )

    @staticmethod
    def validate_values(
        *,
        welcome_rox: Decimal,
        first_line_percent: Decimal,
        topup_partner_rox: Decimal,
        topup_user_rox: Decimal,
        topup_user_min_rub: Decimal,
    ) -> None:
        if welcome_rox < 0 or welcome_rox > Decimal("100000"):
            raise ValueError("Welcome ROX must be between 0 and 100000")
        if first_line_percent < 0 or first_line_percent > Decimal("100"):
            raise ValueError("First-line percent must be between 0 and 100")
        if topup_partner_rox < 0 or topup_partner_rox > Decimal("100000"):
            raise ValueError("Partner top-up ROX must be between 0 and 100000")
        if topup_user_rox < 0 or topup_user_rox > Decimal("100000"):
            raise ValueError("User top-up ROX must be between 0 and 100000")
        if topup_user_min_rub < 0 or topup_user_min_rub > Decimal("100000000"):
            raise ValueError("User top-up minimum RUB must be between 0 and 100000000")

    @staticmethod
    def validate_referral_terms(
        *,
        first_line_percent: Decimal,
        second_line_percent: Decimal,
    ) -> None:
        if first_line_percent < 0 or first_line_percent > Decimal("100"):
            raise ValueError("First-line percent must be between 0 and 100")
        if second_line_percent < 0 or second_line_percent > Decimal("100"):
            raise ValueError("Second-line percent must be between 0 and 100")

    @staticmethod
    def view(config: PartnerPromoProgramConfig) -> dict[str, object]:
        return {
            "key": config.key,
            "welcome_rox": str(config.welcome_rox),
            "first_line_percent": str(config.first_line_percent),
            "topup_partner_rox": str(config.topup_partner_rox),
            "topup_user_rox": str(config.topup_user_rox),
            "topup_user_min_rub": str(config.topup_user_min_rub),
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
        }

    @staticmethod
    def terms_view(terms: PartnerReferralTerms) -> dict[str, object]:
        return {
            "user_id": str(terms.user_id),
            "first_line_percent": str(terms.first_line_percent),
            "second_line_percent": str(terms.second_line_percent),
            "created_at": terms.created_at.isoformat(),
            "updated_at": terms.updated_at.isoformat(),
        }
