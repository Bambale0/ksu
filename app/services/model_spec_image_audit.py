from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

_INSTALLED = False


def install_model_spec_image_audit() -> None:
    """Restore provider-supported image controls and current request limits."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_image_contracts as image_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    gpt2_ids = {"gpt-image-2-t2i", "gpt-image-2-i2i"}
    wan_ids = {"wan-2.7-image", "wan-2.7-image-pro"}
    patched = []
    for spec in catalog.SPECS:
        if spec.id in gpt2_ids and "resolution" not in spec.known_fields:
            fields = list(spec.known_fields)
            fields.append("resolution")
            spec = replace(spec, known_fields=tuple(fields))
        patched.append(spec)
    catalog.SPECS = tuple(patched)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    for model_id in gpt2_ids:
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})[
            "resolution"
        ] = ["1K", "2K", "4K"]
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["resolution"] = "1K"

    # Current Kie upload limits. These are surfaced to every dynamic client via
    # ui_schema instead of being reimplemented in the Mini App.
    nano_lite = ui_contract.MODEL_FIELD_OVERRIDES.setdefault("nano-banana-2-lite", {})
    nano_lite["image_urls"] = {"max_items": 10, "max_size_mb": 30}

    for model_id in wan_ids:
        overrides = ui_contract.MODEL_FIELD_OVERRIDES.setdefault(model_id, {})
        overrides["input_urls"] = {"max_items": 9, "max_size_mb": 10}
        overrides["prompt"] = {"max_length": 5000}

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        previous_rules(spec, clean)
        if spec.id in wan_ids:
            prompt = str(clean.get("prompt") or "")
            if not 1 <= len(prompt) <= 5000:
                raise catalog.InvalidModelParametersError(
                    "WAN 2.7 Image prompt must be between 1 and 5000 characters"
                )

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_normalize = image_contracts.normalize_kie_image_input

    def audited_normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model in {"wan/2-7-image", "wan/2-7-image-pro"}:
            prompt = str(source.get("prompt") or "")
            if not 1 <= len(prompt) <= 5000:
                raise image_contracts.KieImageContractError(
                    "WAN 2.7 Image prompt must be between 1 and 5000 characters"
                )
        return previous_normalize(model, source)

    image_contracts.normalize_kie_image_input = audited_normalize
