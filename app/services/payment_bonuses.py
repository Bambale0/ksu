from __future__ import annotations

from decimal import Decimal


class TopUpBonusService:
    """Legacy compatibility shim.

    Automatic package bonuses are disabled. Promotional ROX may only be granted
    through a valid promo code attached to a successfully paid top-up.
    """

    BONUS_ROX_BY_BASE_CREDITS: dict[Decimal, Decimal] = {}

    @classmethod
    def bonus_for(cls, credits: Decimal | int | str) -> Decimal:
        _ = credits
        return Decimal("0")

    @classmethod
    def total_for(cls, credits: Decimal | int | str) -> Decimal:
        return Decimal(str(credits))
