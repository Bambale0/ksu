from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_INSTALLED = False


def install_model_spec_pricing_audit() -> None:
    """Apply published mode/resolution pricing tiers to the validated request.

    Admin tariffs have long accepted ``by_mode`` and ``by_resolution`` sections,
    but the runtime used only the base flat/per-second price. Resolve tiers only
    after ModelCatalog validation so pricing sees normalized provider values.
    Resolution is the final override when both dimensions are present, giving a
    deterministic and more specific output-quality price.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_catalog as catalog

    previous_prepare = catalog.ModelCatalog.prepare

    def audited_prepare(
        cls: type[catalog.ModelCatalog],
        model_id: str,
        parameters: dict[str, Any],
        *,
        billing_seconds: int | None = None,
    ):
        spec, clean, cost, seconds, unit_price = previous_prepare(
            model_id,
            parameters,
            billing_seconds=billing_seconds,
        )
        override = cls._pricing_overrides().get(spec.id)
        if not isinstance(override, dict):
            return spec, clean, cost, seconds, unit_price

        tier_price: Decimal | None = None
        for section, field in (("by_mode", "mode"), ("by_resolution", "resolution")):
            tiers = override.get(section)
            value = clean.get(field)
            if not isinstance(tiers, dict) or value in (None, ""):
                continue
            matched = tiers.get(str(value))
            if matched is None:
                continue
            tier_price = Decimal(str(matched))

        if tier_price is None:
            return spec, clean, cost, seconds, unit_price
        if tier_price <= 0:
            raise catalog.InvalidModelParametersError("Model tier price must be positive")

        if spec.price_mode == "per_second":
            if seconds is None:
                raise catalog.InvalidModelParametersError("Video duration is required for billing")
            cost = (tier_price * Decimal(seconds)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            cost = tier_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return spec, clean, cost, seconds, tier_price

    catalog.ModelCatalog.prepare = classmethod(audited_prepare)
