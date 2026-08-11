from decimal import Decimal, ROUND_HALF_UP

from app.core.config import settings

MONEY_QUANT = Decimal("0.01")
CREDIT_QUANT = Decimal("0.01")


class InternalCreditService:
    @staticmethod
    def rub_per_credit() -> Decimal:
        rate = Decimal(settings.internal_credit_rub)
        if rate <= 0:
            raise ValueError("INTERNAL_CREDIT_RUB must be positive")
        return rate

    @classmethod
    def rubles_for(cls, credits: Decimal | int | str) -> Decimal:
        value = Decimal(str(credits))
        if value < 0:
            raise ValueError("Credits cannot be negative")
        return (value * cls.rub_per_credit()).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def credits_for(cls, rubles: Decimal | int | str) -> Decimal:
        value = Decimal(str(rubles))
        if value < 0:
            raise ValueError("Rubles cannot be negative")
        return (value / cls.rub_per_credit()).quantize(CREDIT_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def assert_rate(cls, *, credits: Decimal, rubles: Decimal) -> None:
        expected = cls.rubles_for(credits)
        actual = Decimal(rubles).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        if expected != actual:
            raise ValueError(
                f"Package violates internal credit rate: {credits} credits must cost {expected} RUB"
            )
