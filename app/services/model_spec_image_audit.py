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
    nano_legacy_ids = {"nano-banana", "nano-banana-edit"}
    nexus_nano_ids = {"nano-banana-pro", "nano-banana-2"}
    nexus_nano_ratios = [
        "auto",
        "1:1",
        "2:3",
        "3:2",
        "3:4",
        "4:3",
        "4:5",
        "5:4",
        "9:16",
        "16:9",
        "21:9",
    ]
    nexus_nano_resolutions = {"1K", "2K", "4K"}
    wan_ids = {"wan-2.7-image", "wan-2.7-image-pro"}
    nsfw_image_ids = {
        *nano_legacy_ids,
        "seedream-4-t2i",
        "seedream-4-edit",
        "seedream-4.5-t2i",
        "seedream-4.5-edit",
        "seedream-5-lite-t2i",
        "seedream-5-lite-i2i",
        "seedream-5-pro-t2i",
        "seedream-5-pro-i2i",
        *wan_ids,
        "grok-image-t2i",
        "grok-image-i2i",
    }
    patched = []
    for spec in catalog.SPECS:
        fields = list(spec.known_fields)
        changed = False
        if spec.id in gpt2_ids and "resolution" not in fields:
            fields.append("resolution")
            changed = True
        if spec.id in nano_legacy_ids and "nsfw_checker" not in fields:
            fields.append("nsfw_checker")
            changed = True
        if spec.id in nexus_nano_ids and "output_format" in fields:
            # Nexus Nano Banana does not expose output_format. Keep legacy
            # request payloads tolerated by ModelCatalog.prepare(), but stop
            # advertising a control that the provider cannot honor.
            fields.remove("output_format")
            changed = True
        if changed:
            spec = replace(spec, known_fields=tuple(fields))
        patched.append(spec)
    catalog.SPECS = tuple(patched)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    for model_id in gpt2_ids:
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})[
            "resolution"
        ] = ["1K", "2K", "4K"]
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["resolution"] = "1K"

    for model_id in nexus_nano_ids:
        suggestions = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})
        suggestions["aspect_ratio"] = list(nexus_nano_ratios)
        suggestions["resolution"] = ["1K", "2K", "4K"]
        suggestions.pop("output_format", None)
        defaults = ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})
        defaults.pop("output_format", None)
        if str(defaults.get("aspect_ratio") or "1:1") not in nexus_nano_ratios:
            defaults["aspect_ratio"] = "1:1"

    for model_id in nsfw_image_ids:
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["nsfw_checker"] = False

    # Provider-specific upload limits are surfaced to every dynamic client via
    # ui_schema instead of being reimplemented in the Mini App.
    upload_limits = {
        "nano-banana-edit": ("image_urls", 10, 10),
        "nano-banana-pro": ("image_input", 4, 30),
        "nano-banana-2": ("image_input", 4, 30),
        "nano-banana-2-lite": ("image_urls", 10, 30),
        "seedream-4.5-edit": ("image_urls", 14, 10),
        "seedream-5-lite-i2i": ("image_urls", 14, 30),
        "seedream-5-pro-i2i": ("image_urls", 10, 10),
        "gpt-image-1.5-i2i": ("input_urls", 16, 10),
        "gpt-image-2-i2i": ("input_urls", 16, 30),
        "grok-image-i2i": ("image_urls", 1, 10),
    }
    for model_id, (field, max_items, max_size_mb) in upload_limits.items():
        ui_contract.MODEL_FIELD_OVERRIDES.setdefault(model_id, {})[field] = {
            "max_items": max_items,
            "max_size_mb": max_size_mb,
        }

    for model_id in wan_ids:
        overrides = ui_contract.MODEL_FIELD_OVERRIDES.setdefault(model_id, {})
        overrides["input_urls"] = {"max_items": 9, "max_size_mb": 10}
        overrides["prompt"] = {"max_length": 5000}

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        previous_rules(spec, clean)
        if spec.id in nsfw_image_ids:
            nsfw = clean.get("nsfw_checker")
            if nsfw is not None and not isinstance(nsfw, bool):
                raise catalog.InvalidModelParametersError("nsfw_checker must be boolean")
        if spec.id in nexus_nano_ids:
            refs = clean.get("image_input") or []
            if not isinstance(refs, list):
                raise catalog.InvalidModelParametersError("image_input must be an array")
            if len(refs) > 4:
                raise catalog.InvalidModelParametersError(
                    "Nexus Nano Banana accepts at most four image references"
                )
            aspect_ratio = str(clean.get("aspect_ratio") or "1:1")
            if aspect_ratio not in nexus_nano_ratios:
                raise catalog.InvalidModelParametersError(
                    f"Unsupported Nexus Nano Banana aspect_ratio={aspect_ratio!r}"
                )
            resolution = str(clean.get("resolution") or "1K").upper()
            if resolution not in nexus_nano_resolutions:
                raise catalog.InvalidModelParametersError(
                    f"Unsupported Nexus Nano Banana resolution={resolution!r}"
                )
            if "resolution" in clean:
                clean["resolution"] = resolution
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
        provider_nsfw_models = {
            "google/nano-banana",
            "google/nano-banana-edit",
            "bytedance/seedream-v4-text-to-image",
            "bytedance/seedream-v4-edit",
            "seedream/4.5-text-to-image",
            "seedream/4.5-edit",
            "seedream/5-lite-text-to-image",
            "seedream/5-lite-image-to-image",
            "seedream/5-pro-text-to-image",
            "seedream/5-pro-image-to-image",
            "wan/2-7-image",
            "wan/2-7-image-pro",
            "grok-imagine/text-to-image",
            "grok-imagine/image-to-image",
        }
        if model in provider_nsfw_models:
            nsfw = source.get("nsfw_checker")
            if nsfw is not None and not isinstance(nsfw, bool):
                raise image_contracts.KieImageContractError("nsfw_checker must be boolean")
        if model in {"wan/2-7-image", "wan/2-7-image-pro"}:
            prompt = str(source.get("prompt") or "")
            if not 1 <= len(prompt) <= 5000:
                raise image_contracts.KieImageContractError(
                    "WAN 2.7 Image prompt must be between 1 and 5000 characters"
                )
        return previous_normalize(model, source)

    image_contracts.normalize_kie_image_input = audited_normalize
