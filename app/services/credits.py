from decimal import Decimal, ROUND_HALF_UP

from app.core.config import settings

MONEY_QUANT = Decimal("0.01")
CREDIT_QUANT = Decimal("0.01")
LEGACY_RUB_PER_CREDIT = Decimal("10")


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
    def legacy_credits_to_rox(cls, credits: Decimal | int | str) -> Decimal:
        """Convert one pre-ROXY 10-RUB credit amount to the public 1-RUB ROX unit.

        Price definitions that still live in source/config can use this helper while
        persisted balances/history are converted once by Alembic migration 0023.
        """
        value = Decimal(str(credits))
        if value < 0:
            raise ValueError("Credits cannot be negative")
        rubles = value * LEGACY_RUB_PER_CREDIT
        return (rubles / cls.rub_per_credit()).quantize(CREDIT_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def legacy_package_credits(cls, *, credits: Decimal, rubles: Decimal) -> Decimal | None:
        """Return redenominated ROX only for an exact legacy 10-RUB package pair."""
        value = Decimal(str(credits))
        amount = Decimal(str(rubles)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        legacy_amount = (value * LEGACY_RUB_PER_CREDIT).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        if amount != legacy_amount:
            return None
        return cls.credits_for(amount)

    @classmethod
    def assert_rate(cls, *, credits: Decimal, rubles: Decimal) -> None:
        expected = cls.rubles_for(credits)
        actual = Decimal(rubles).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        if expected != actual:
            raise ValueError(
                f"Package violates internal credit rate: {credits} credits must cost {expected} RUB"
            )
