"""User-facing aspect-ratio policy, separate from frozen provider contracts."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


def is_auto_aspect_ratio(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() == "auto"


def explicit_aspect_ratio_options(model_id: str) -> list[str]:
    # Resolve at call time: startup contract installers own the effective catalog.
    from app.services.model_catalog import ModelCatalog, UnknownModelError
    from app.services.model_ui import FIELD_DEFINITIONS
    from app.services.model_ui_contract import MODEL_FIELD_SUGGESTIONS

    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return []
    if "aspect_ratio" not in spec.known_fields:
        return []
    suggestions = MODEL_FIELD_SUGGESTIONS.get(model_id, {}).get(
        "aspect_ratio", FIELD_DEFINITIONS["aspect_ratio"].get("suggestions", [])
    )
    return list(dict.fromkeys(
        str(value).strip() for value in suggestions
        if str(value).strip() and not is_auto_aspect_ratio(value)
    ))


def requires_explicit_aspect_ratio(model_id: str) -> bool:
    from app.services.model_catalog import ModelCatalog, UnknownModelError
    from app.services.model_ui_contract import MODEL_DEFAULTS

    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return False
    return "aspect_ratio" in spec.known_fields and is_auto_aspect_ratio(
        MODEL_DEFAULTS.get(model_id, {}).get("aspect_ratio")
    )


def sanitize_aspect_ratio_parameters(parameters: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(parameters or {})
    if is_auto_aspect_ratio(result.get("aspect_ratio")):
        result.pop("aspect_ratio")
    return result


def sanitize_aspect_ratio_schema(
    model_id: str, schema: Mapping[str, Any], *, require_choice: bool = False,
) -> dict[str, Any]:
    result = deepcopy(dict(schema))
    defaults = result.get("defaults") or {}
    required = (
        require_choice
        or is_auto_aspect_ratio(defaults.get("aspect_ratio"))
        or requires_explicit_aspect_ratio(model_id)
    )
    result["defaults"] = sanitize_aspect_ratio_parameters(defaults)
    if require_choice:
        result["defaults"].pop("aspect_ratio", None)
    for field in result.get("fields", []):
        if field.get("name") != "aspect_ratio":
            continue
        field["suggestions"] = [
            value for value in field.get("suggestions", []) if not is_auto_aspect_ratio(value)
        ]
        if is_auto_aspect_ratio(field.get("default")) or require_choice:
            field.pop("default", None)
        if required:
            field["required"] = True
    return result


def validate_generation_aspect_ratio(
    model_id: str, parameters: Mapping[str, Any] | None,
) -> None:
    from app.services.model_catalog import InvalidModelParametersError, ModelCatalog

    value = (parameters or {}).get("aspect_ratio")
    if is_auto_aspect_ratio(value):
        raise InvalidModelParametersError("Автоматическое соотношение сторон больше недоступно. Выберите формат изображения или видео.")
    missing = value is None or (isinstance(value, str) and not value.strip())
    if missing:
        if requires_explicit_aspect_ratio(model_id):
            raise InvalidModelParametersError("Выберите соотношение сторон перед запуском.")
        return
    options = explicit_aspect_ratio_options(model_id)
    if options and value not in options:
        # Seedance's technical adaptive mode predates this UI policy. Some
        # public cards list only fixed ratios, so leave that mode to the
        # existing provider/model contract instead of widening this change.
        spec = ModelCatalog.get(model_id)
        if value == "adaptive" and spec.family == "seedance" and spec.operation == "multimodal_video":
            return
        raise InvalidModelParametersError("Недопустимое соотношение сторон. Выберите доступный формат.")
