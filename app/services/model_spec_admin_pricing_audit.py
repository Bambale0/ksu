from __future__ import annotations

from typing import Any

_INSTALLED = False


def install_model_spec_admin_pricing_audit() -> None:
    """Reject tariff tiers that cannot be selected by the target model.

    The admin tariff API supports by_mode/by_resolution. Validate those tier
    keys against the same public ui_schema used by the Mini App so a published
    tariff cannot silently target impossible provider values.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import admin_pricing
    from app.services.model_catalog import ModelCatalog
    from app.services.model_ui_contract import build_public_model_ui_schema

    previous_validate = admin_pricing.validate_tariff_payload

    def audited_validate(payload: dict[str, Any]) -> dict[str, Any]:
        validated = previous_validate(payload)
        pricing = validated.get("generation_pricing")
        if not isinstance(pricing, dict):
            return validated

        for model_id, override in pricing.items():
            if not isinstance(override, dict):
                continue
            spec = ModelCatalog.get(str(model_id))
            schema = build_public_model_ui_schema(spec.public_dict())
            fields = {
                str(field.get("name")): field
                for field in schema.get("fields", [])
                if isinstance(field, dict)
            }
            for section, parameter in (("by_mode", "mode"), ("by_resolution", "resolution")):
                tiers = override.get(section)
                if not isinstance(tiers, dict):
                    continue
                field = fields.get(parameter) or {}
                suggestions = field.get("suggestions")
                if not isinstance(suggestions, list) or not suggestions:
                    continue
                allowed = {str(value) for value in suggestions}
                invalid = sorted(str(value) for value in tiers if str(value) not in allowed)
                if invalid:
                    raise admin_pricing.TariffValidationError(
                        f"generation_pricing.{model_id}.{section} contains unsupported "
                        f"{parameter} values: {', '.join(invalid)}"
                    )
        return validated

    admin_pricing.validate_tariff_payload = audited_validate
