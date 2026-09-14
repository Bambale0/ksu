from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


class TopUpBonusService:
    """Automatic package gift shown directly on each top-up price.

    Product rule: every paid package receives +10% ROX. Examples:
    100 -> +10, 300 -> +30, 500 -> +50, 1000 -> +100.
    Promo codes are a separate additive bonus handled by PromoCodeService.
    """

    BONUS_RATE = Decimal("0.10")

    @classmethod
    def bonus_for(cls, credits: Decimal | int | str) -> Decimal:
        base = Decimal(str(credits))
        if base <= 0:
            return Decimal("0")
        return (base * cls.BONUS_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def total_for(cls, credits: Decimal | int | str) -> Decimal:
        base = Decimal(str(credits))
        return base + cls.bonus_for(base)
