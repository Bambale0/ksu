from __future__ import annotations

from decimal import Decimal


class TopUpBonusService:
    """Default ordinary package bonus schedule.

    Package configuration may override bonus_credits explicitly. These defaults
    keep existing production package JSON backward-compatible. Partner promo
    bonuses are a separate payment-time layer.
    """

    BONUS_ROX_BY_BASE_CREDITS: dict[Decimal, Decimal] = {
        Decimal("300"): Decimal("30"),
        Decimal("500"): Decimal("50"),
        Decimal("1000"): Decimal("100"),
        Decimal("2000"): Decimal("150"),
        Decimal("5000"): Decimal("200"),
    }

    @classmethod
    def bonus_for(cls, credits: Decimal | int | str) -> Decimal:
        return cls.BONUS_ROX_BY_BASE_CREDITS.get(Decimal(str(credits)), Decimal("0"))

    @classmethod
    def total_for(cls, credits: Decimal | int | str) -> Decimal:
        base = Decimal(str(credits))
        return base + cls.bonus_for(base)
