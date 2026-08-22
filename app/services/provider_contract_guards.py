from __future__ import annotations

from typing import Any

_INSTALLED = False


def install_provider_contract_guards() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_catalog as catalog
    from app.services import model_routing as routing
    from app.services import model_ui as model_ui
    from app.services import model_ui_contract as ui_contract

    # Wan Video Edit exposes a scalar provider enum, not an arbitrary JSON object.
    model_ui.FIELD_DEFINITIONS["audio_setting"] = {
        "label": "Аудио",
        "control": "combobox",
        "group": "output",
        "suggestions": ["auto", "origin"],
    }
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("wan-2.7-video-edit", {})[
        "audio_setting"
    ] = ["auto", "origin"]
    ui_contract.MODEL_DEFAULTS.setdefault("wan-2.7-video-edit", {})[
        "audio_setting"
    ] = "auto"

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def guarded_rules(spec: Any, clean: dict[str, Any]) -> None:
        previous_rules(spec, clean)
        if spec.id in {"wan-2.7-image", "wan-2.7-image-pro"}:
            has_images = bool(clean.get("input_urls"))
            gallery = bool(clean.get("enable_sequential"))
            if bool(clean.get("thinking_mode")) and (has_images or gallery):
                raise catalog.InvalidModelParametersError(
                    "Wan thinking_mode доступен только для одиночной text-to-image генерации без референсов"
                )
            if spec.id == "wan-2.7-image-pro" and has_images and str(clean.get("resolution") or "") == "4K":
                raise catalog.InvalidModelParametersError(
                    "Wan 2.7 Pro 4K доступен только без входных изображений; для редактирования выберите 1K или 2K"
                )

    catalog.ModelCatalog._validate_model_rules = guarded_rules

    previous_mode_for = routing._mode_for

    def mode_for(spec: Any, parameters: dict[str, Any], input_url: str | None) -> str:
        if spec.id == "grok-video-i2v" and parameters.get("task_id"):
            return "i2v"
        return previous_mode_for(spec, parameters, input_url)

    routing._mode_for = mode_for

    # Remove stale/orphan defaults whenever a provider field was removed from the
    # current public schema. Drafts then contain exactly what users can see/edit.
    previous_public_schema = ui_contract.build_public_model_ui_schema

    def sanitized_public_schema(model: dict[str, Any]) -> dict[str, Any]:
        schema = previous_public_schema(model)
        field_names = {str(field.get("name") or "") for field in schema.get("fields", [])}
        schema["defaults"] = {
            key: value
            for key, value in dict(schema.get("defaults", {})).items()
            if key in field_names
        }
        return schema

    ui_contract.build_public_model_ui_schema = sanitized_public_schema
