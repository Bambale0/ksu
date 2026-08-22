from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_INSTALLED = False


def install_model_spec_pricing_audit() -> None:
    """Apply published mode/resolution pricing tiers to every billing path.

    Admin tariffs support ``by_mode`` and ``by_resolution``. Resolve tiers only
    after model validation so pricing sees normalized provider values. Resolution
    is the final override when both dimensions are configured, and both the raw
    ModelCatalog path and GenerationService quote/create path use that same rule.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_catalog as catalog
    from app.services.generations import GenerationService

    def tier_price_for(model_id: str, parameters: dict[str, Any]) -> Decimal | None:
        override = catalog.ModelCatalog._pricing_overrides().get(model_id)
        if not isinstance(override, dict):
            return None

        tier_price: Decimal | None = None
        for section, field in (("by_mode", "mode"), ("by_resolution", "resolution")):
            tiers = override.get(section)
            value = parameters.get(field)
            if not isinstance(tiers, dict) or value in (None, ""):
                continue
            matched = tiers.get(str(value))
            if matched is not None:
                tier_price = Decimal(str(matched))
        if tier_price is not None and tier_price <= 0:
            raise catalog.InvalidModelParametersError("Model tier price must be positive")
        return tier_price

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
        tier_price = tier_price_for(spec.id, clean)
        if tier_price is None:
            return spec, clean, cost, seconds, unit_price

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

    previous_effective_unit_price = GenerationService._effective_unit_price

    @staticmethod
    def audited_effective_unit_price(
        *,
        model_id: str,
        parameters: dict[str, Any],
    ) -> Decimal:
        tier_price = tier_price_for(model_id, parameters)
        if tier_price is not None:
            return tier_price
        return previous_effective_unit_price(model_id=model_id, parameters=parameters)

    GenerationService._effective_unit_price = audited_effective_unit_price
