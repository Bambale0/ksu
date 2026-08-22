from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

_INSTALLED = False


def install_model_spec_gemini_audit() -> None:
    """Expose and enforce the current Gemini Omni Video request contract."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    patched = []
    for spec in catalog.SPECS:
        if spec.id == "gemini-omni-video":
            fields = list(spec.known_fields)
            for field in ("aspect_ratio", "resolution", "seed"):
                if field not in fields:
                    fields.append(field)
            spec = replace(
                spec,
                known_fields=tuple(fields),
                min_seconds=4,
                max_seconds=10,
            )
        patched.append(spec)
    catalog.SPECS = tuple(patched)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    ui_contract.KIE_DURATION_OPTIONS["gemini-omni-video"] = [4, 6, 8, 10]
    suggestions = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("gemini-omni-video", {})
    suggestions["aspect_ratio"] = ["16:9", "9:16"]
    suggestions["resolution"] = ["720p", "1080p", "4k"]
    defaults = ui_contract.MODEL_DEFAULTS.setdefault("gemini-omni-video", {})
    defaults.update({"duration": 4, "aspect_ratio": "16:9", "resolution": "720p"})
    overrides = ui_contract.MODEL_FIELD_OVERRIDES.setdefault("gemini-omni-video", {})
    overrides["image_urls"] = {"max_items": 7, "max_size_mb": 10}
    overrides["audio_ids"] = {"max_items": 1}
    overrides["video_list"] = {"max_items": 1}
    overrides["character_ids"] = {"max_items": 3}
    overrides["seed"] = {"min": 0, "max": 2147483647, "step": 1}

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        previous_rules(spec, clean)
        if spec.id != "gemini-omni-video":
            return

        try:
            duration = int(clean.get("duration"))
        except (TypeError, ValueError) as exc:
            raise catalog.InvalidModelParametersError(
                "Gemini Omni duration must be 4, 6, 8 or 10 seconds"
            ) from exc
        if duration not in {4, 6, 8, 10}:
            raise catalog.InvalidModelParametersError(
                "Gemini Omni duration must be 4, 6, 8 or 10 seconds"
            )

        if str(clean.get("aspect_ratio") or "16:9") not in {"16:9", "9:16"}:
            raise catalog.InvalidModelParametersError(
                "Gemini Omni aspect_ratio must be 16:9 or 9:16"
            )
        if str(clean.get("resolution") or "720p") not in {"720p", "1080p", "4k"}:
            raise catalog.InvalidModelParametersError(
                "Gemini Omni resolution must be 720p, 1080p or 4k"
            )

        seed = clean.get("seed")
        if seed not in (None, ""):
            try:
                seed_value = int(seed)
            except (TypeError, ValueError) as exc:
                raise catalog.InvalidModelParametersError(
                    "Gemini Omni seed must be an integer"
                ) from exc
            if not 0 <= seed_value <= 2147483647:
                raise catalog.InvalidModelParametersError(
                    "Gemini Omni seed must be between 0 and 2147483647"
                )

        audio_ids = clean.get("audio_ids") or []
        if not isinstance(audio_ids, list) or len(audio_ids) > 1:
            raise catalog.InvalidModelParametersError(
                "Gemini Omni accepts at most one audio ID"
            )

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_normalize = video_contracts.normalize_kie_video_input

    def audited_normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model != "gemini-omni-video":
            return previous_normalize(model, source)

        try:
            duration = int(source.get("duration"))
        except (TypeError, ValueError) as exc:
            raise video_contracts.KieVideoContractError(
                "Gemini Omni duration must be 4, 6, 8 or 10 seconds"
            ) from exc
        if duration not in {4, 6, 8, 10}:
            raise video_contracts.KieVideoContractError(
                "Gemini Omni duration must be 4, 6, 8 or 10 seconds"
            )
        source["duration"] = str(duration)

        aspect_ratio = str(source.get("aspect_ratio") or "16:9")
        if aspect_ratio not in {"16:9", "9:16"}:
            raise video_contracts.KieVideoContractError(
                "Gemini Omni aspect_ratio must be 16:9 or 9:16"
            )
        source["aspect_ratio"] = aspect_ratio

        resolution = str(source.get("resolution") or "720p")
        if resolution not in {"720p", "1080p", "4k"}:
            raise video_contracts.KieVideoContractError(
                "Gemini Omni resolution must be 720p, 1080p or 4k"
            )
        source["resolution"] = resolution

        seed = source.get("seed")
        if seed not in (None, ""):
            try:
                seed_value = int(seed)
            except (TypeError, ValueError) as exc:
                raise video_contracts.KieVideoContractError(
                    "Gemini Omni seed must be an integer"
                ) from exc
            if not 0 <= seed_value <= 2147483647:
                raise video_contracts.KieVideoContractError(
                    "Gemini Omni seed must be between 0 and 2147483647"
                )
            source["seed"] = seed_value

        audio_ids = source.get("audio_ids") or []
        if not isinstance(audio_ids, list) or len(audio_ids) > 1:
            raise video_contracts.KieVideoContractError(
                "Gemini Omni accepts at most one audio ID"
            )

        return previous_normalize(model, source)

    video_contracts.normalize_kie_video_input = audited_normalize
