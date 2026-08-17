from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.model_ui import build_model_ui_schema

SEEDANCE_MODELS = {
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
}


def _patch_field(schema: dict[str, Any], name: str, **values: Any) -> None:
    for field in schema.get("fields", []):
        if field.get("name") == name:
            field.update(values)
            return


def build_public_model_ui_schema(model: dict[str, Any]) -> dict[str, Any]:
    schema = deepcopy(build_model_ui_schema(model))
    model_id = str(model["id"])

    scenario = schema.get("scenario")
    if isinstance(scenario, dict):
        for item in scenario.get("items", []):
            visible = list(item.get("visible_fields", []))
            scenario_id = str(item.get("id") or "")
            if model_id in SEEDANCE_MODELS:
                if scenario_id == "references":
                    item["required_any"] = visible
                elif scenario_id != "text":
                    item["required_fields"] = visible
            elif model_id == "wan-2.7-i2v":
                item["required_fields"] = visible

    if model_id in {"kling-motion-2.6", "kling-motion-3.0"}:
        _patch_field(schema, "input_urls", max_size_mb=10, max_items=1)
        _patch_field(schema, "video_urls", max_size_mb=100, max_items=1)

    if model_id == "kling-3.0":
        _patch_field(schema, "image_urls", label="Первый / последний кадр", max_items=2, max_size_mb=10)
        _patch_field(
            schema,
            "mode",
            label="Качество",
            control="combobox",
            group="output",
            suggestions=["std", "pro", "4K"],
        )
        _patch_field(
            schema,
            "aspect_ratio",
            suggestions=["16:9", "9:16", "1:1"],
        )
        _patch_field(schema, "sound", label="Нативный звук", control="toggle", group="output")
        _patch_field(schema, "multi_shots", label="Multi-shot", control="toggle", group="output")
        _patch_field(
            schema,
            "multi_prompt",
            label="Кадры multi-shot",
            control="json",
            group="advanced",
            placeholder='[{"prompt":"...","duration":3}]',
        )
        _patch_field(
            schema,
            "kling_elements",
            label="Element references",
            control="json",
            group="references",
            placeholder='[{"name":"hero","description":"...","element_input_urls":["...","..."]}]',
        )
        schema["defaults"] = {
            **schema.get("defaults", {}),
            "mode": "pro",
            "aspect_ratio": "16:9",
            "sound": True,
            "multi_shots": False,
        }

    if model_id == "veo-3.1":
        _patch_field(schema, "image_urls", label="Кадры / референсы", max_items=3)
        _patch_field(
            schema,
            "veo_model",
            label="Версия Veo",
            control="combobox",
            group="output",
            suggestions=["veo3", "veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"],
        )
        _patch_field(
            schema,
            "watermark_text",
            label="Водяной знак",
            control="text",
            group="advanced",
        )
        _patch_field(
            schema,
            "aspect_ratio",
            suggestions=["16:9", "9:16", "Auto"],
        )
        _patch_field(
            schema,
            "enable_fallback",
            label="Fallback",
            control="toggle",
            group="advanced",
        )
        _patch_field(
            schema,
            "enable_translation",
            label="Автоперевод промпта",
            control="toggle",
            group="advanced",
        )
        _patch_field(
            schema,
            "generation_type",
            label="Режим генерации",
            control="combobox",
            group="references",
            suggestions=[
                "TEXT_2_VIDEO",
                "FIRST_AND_LAST_FRAMES_2_VIDEO",
                "REFERENCE_2_VIDEO",
            ],
        )
        schema["defaults"] = {
            **schema.get("defaults", {}),
            "veo_model": "veo3_fast",
            "aspect_ratio": "16:9",
            "enable_fallback": False,
            "enable_translation": True,
            "generation_type": "TEXT_2_VIDEO",
        }

    if model_id == "gemini-omni-video":
        _patch_field(schema, "image_urls", label="Изображения", max_items=7)
        _patch_field(
            schema,
            "audio_ids",
            label="Gemini Omni audio IDs",
            control="json",
            group="references",
            placeholder='["audio_id"]',
        )
        _patch_field(
            schema,
            "video_list",
            label="Видео-референс",
            control="json",
            group="references",
            placeholder='[{"url":"https://...","start":0,"ends":10}]',
        )
        _patch_field(
            schema,
            "character_ids",
            label="Character IDs",
            control="json",
            group="references",
            placeholder='["character_id"]',
        )

    return schema
