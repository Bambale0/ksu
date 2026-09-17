from __future__ import annotations

from decimal import Decimal


class TopUpBonusService:
    """Compatibility helper with no embedded business schedule.

    Payment-package bonuses are owned by the published admin tariff. Callers that
    still use this helper must pass the configured value explicitly.
    """

    @staticmethod
    def bonus_for(
        credits: Decimal | int | str,
        *,
        configured_bonus: Decimal | int | str | None = None,
    ) -> Decimal:
        _ = Decimal(str(credits))
        if configured_bonus is None:
            return Decimal("0")
        bonus = Decimal(str(configured_bonus))
        if bonus < 0:
            raise ValueError("Configured package bonus must be non-negative")
        return bonus

    @classmethod
    def total_for(
        cls,
        credits: Decimal | int | str,
        *,
        configured_bonus: Decimal | int | str | None = None,
    ) -> Decimal:
        base = Decimal(str(credits))
        return base + cls.bonus_for(base, configured_bonus=configured_bonus)
