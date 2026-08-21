from __future__ import annotations

from decimal import Decimal


class TopUpBonusService:
    """Operator-owned ROX gift bonuses for wallet top-up packages."""

    BONUS_ROX_BY_BASE_CREDITS: dict[Decimal, Decimal] = {
        Decimal("300"): Decimal("50"),
        Decimal("500"): Decimal("100"),
        Decimal("1000"): Decimal("150"),
        Decimal("2000"): Decimal("200"),
        Decimal("5000"): Decimal("500"),
    }

    @classmethod
    def bonus_for(cls, credits: Decimal | int | str) -> Decimal:
        return cls.BONUS_ROX_BY_BASE_CREDITS.get(Decimal(str(credits)), Decimal("0"))

    @classmethod
    def total_for(cls, credits: Decimal | int | str) -> Decimal:
        base = Decimal(str(credits))
        return base + cls.bonus_for(base)
