from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

_INSTALLED = False

SEEDANCE20_IDS = {"seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"}
SEEDANCE20_PROVIDERS = {
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
}


def install_model_spec_current_surface_audit() -> None:
    """Final public-surface corrections from the live Kie model pages.

    This runs after the earlier audit installers so a stale compatibility layer
    cannot re-expose fields that the current provider schema no longer accepts.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    patched_specs = []
    for spec in catalog.SPECS:
        if spec.id in SEEDANCE20_IDS and "return_last_frame" in spec.known_fields:
            spec = replace(
                spec,
                known_fields=tuple(
                    field for field in spec.known_fields if field != "return_last_frame"
                ),
            )
        if spec.id == "veo-3.1":
            fields = list(spec.known_fields)
            for field in ("resolution", "duration"):
                if field not in fields:
                    fields.append(field)
            spec = replace(
                spec,
                known_fields=tuple(fields),
                min_seconds=4,
                max_seconds=8,
            )
        patched_specs.append(spec)

    catalog.SPECS = tuple(patched_specs)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    for model_id in SEEDANCE20_IDS:
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {}).pop("return_last_frame", None)

    veo_fields = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("veo-3.1", {})
    veo_fields["resolution"] = ["720p", "1080p", "4k"]
    ui_contract.KIE_DURATION_OPTIONS["veo-3.1"] = [4, 6, 8]
    ui_contract.MODEL_DEFAULTS.setdefault("veo-3.1", {}).update(
        {"resolution": "720p", "duration": 4}
    )

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        if spec.id in SEEDANCE20_IDS:
            clean.pop("return_last_frame", None)

        if spec.id == "veo-3.1":
            resolution = str(clean.get("resolution") or "720p").lower()
            if resolution not in {"720p", "1080p", "4k"}:
                raise catalog.InvalidModelParametersError(
                    "Veo 3.1 resolution must be 720p, 1080p or 4k"
                )
            clean["resolution"] = resolution

            duration = clean.get("duration", 4)
            try:
                if isinstance(duration, bool):
                    raise TypeError
                duration = int(duration)
            except (TypeError, ValueError) as exc:
                raise catalog.InvalidModelParametersError(
                    "Veo 3.1 duration must be 4, 6 or 8 seconds"
                ) from exc
            if duration not in {4, 6, 8}:
                raise catalog.InvalidModelParametersError(
                    "Veo 3.1 duration must be 4, 6 or 8 seconds"
                )
            clean["duration"] = duration

        previous_rules(spec, clean)

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_video_normalizer = video_contracts.normalize_kie_video_input
    previous_veo_normalizer = video_contracts.normalize_kie_veo_input

    def audited_video_normalizer(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model in SEEDANCE20_PROVIDERS:
            source.pop("return_last_frame", None)
        return previous_video_normalizer(model, source)

    def audited_veo_normalizer(input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        resolution = str(source.get("resolution") or "720p").lower()
        if resolution not in {"720p", "1080p", "4k"}:
            raise video_contracts.KieVideoContractError(
                "Veo 3.1 resolution must be 720p, 1080p or 4k"
            )
        source["resolution"] = resolution

        duration = source.get("duration", 4)
        try:
            if isinstance(duration, bool):
                raise TypeError
            duration = int(duration)
        except (TypeError, ValueError) as exc:
            raise video_contracts.KieVideoContractError(
                "Veo 3.1 duration must be 4, 6 or 8 seconds"
            ) from exc
        if duration not in {4, 6, 8}:
            raise video_contracts.KieVideoContractError(
                "Veo 3.1 duration must be 4, 6 or 8 seconds"
            )
        source["duration"] = duration

        normalized = previous_veo_normalizer(source)
        normalized["resolution"] = resolution
        normalized["duration"] = duration
        return normalized

    video_contracts.normalize_kie_video_input = audited_video_normalizer
    video_contracts.normalize_kie_veo_input = audited_veo_normalizer
