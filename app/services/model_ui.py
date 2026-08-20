from __future__ import annotations

from copy import deepcopy
from typing import Any


FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "prompt": {"label": "Промпт", "control": "textarea", "group": "prompt", "placeholder": "Опишите желаемый результат"},
    "negative_prompt": {"label": "Негативный промпт", "control": "textarea", "group": "advanced"},
    "aspect_ratio": {"label": "Соотношение сторон", "control": "combobox", "group": "output", "suggestions": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"]},
    "resolution": {"label": "Разрешение", "control": "combobox", "group": "output", "suggestions": ["480p", "720p", "1080p", "1K", "2K", "4K"]},
    "quality": {"label": "Качество", "control": "combobox", "group": "output", "suggestions": ["basic", "high"]},
    "output_format": {"label": "Формат результата", "control": "combobox", "group": "output", "suggestions": ["png", "jpeg", "jpg"]},
    "duration": {"label": "Длительность", "control": "number", "group": "output", "step": 1, "suffix": "с"},
    "seed": {"label": "Seed", "control": "number", "group": "advanced", "step": 1, "min": 0, "placeholder": "Случайный"},
    "cfg_scale": {"label": "CFG scale", "control": "number", "group": "advanced", "step": 0.1, "min": 0, "max": 1},
    "n": {"label": "Количество вариантов", "control": "number", "group": "output", "step": 1, "min": 1},
    "enable_sequential": {"label": "Последовательная генерация", "control": "toggle", "group": "advanced"},
    "thinking_mode": {"label": "Thinking mode", "control": "toggle", "group": "advanced"},
    "watermark": {"label": "Водяной знак", "control": "toggle", "group": "advanced"},
    "nsfw_checker": {"label": "NSFW-проверка", "control": "toggle", "group": "advanced"},
    "generate_audio": {"label": "Сгенерировать звук", "control": "toggle", "group": "output"},
    "sound": {"label": "Нативный звук", "control": "toggle", "group": "output"},
    "input_urls": {"label": "Референсы", "control": "files", "group": "references", "accept": "image/*"},
    "image_urls": {"label": "Изображения", "control": "files", "group": "references", "accept": "image/*"},
    "image_input": {"label": "Изображения", "control": "files", "group": "references", "accept": "image/*"},
    "image_url": {"label": "Изображение", "control": "file", "group": "references", "accept": "image/*"},
    "first_frame_url": {"label": "Первый кадр", "control": "file", "group": "references", "accept": "image/*"},
    "last_frame_url": {"label": "Последний кадр", "control": "file", "group": "references", "accept": "image/*"},
    "reference_image_urls": {"label": "Референс-изображения", "control": "files", "group": "references", "accept": "image/*"},
    "reference_video_urls": {"label": "Референс-видео", "control": "files", "group": "references", "accept": "video/*"},
    "reference_audio_urls": {"label": "Референс-аудио", "control": "files", "group": "references", "accept": "audio/*"},
    "video_urls": {"label": "Видео движения", "control": "files", "group": "references", "accept": "video/*"},
    "audio_url": {"label": "Аудио", "control": "file", "group": "references", "accept": "audio/*"},
    "mode": {"label": "Качество", "control": "combobox", "group": "output", "suggestions": ["normal", "720p", "1080p"]},
    "character_orientation": {"label": "Ориентация персонажа", "control": "combobox", "group": "output", "suggestions": ["image", "video"]},
    "background_source": {"label": "Источник фона", "control": "combobox", "group": "output", "suggestions": ["input_video", "input_image"]},
    "multi_shots": {"label": "Multi-shot", "control": "toggle", "group": "output"},
    "multi_prompt": {"label": "Кадры multi-shot", "control": "json", "group": "advanced", "placeholder": '[{"prompt":"...","duration":3}]'},
    "kling_elements": {"label": "Kling Elements", "control": "json", "group": "references"},
    "audio_ids": {"label": "Audio IDs", "control": "json", "group": "references", "placeholder": '["audio_id"]'},
    "video_list": {"label": "Видео-референс", "control": "json", "group": "references", "placeholder": '[{"url":"https://...","start":0,"ends":10}]'},
    "character_ids": {"label": "Character IDs", "control": "json", "group": "references", "placeholder": '["character_id"]'},
    "watermark_text": {"label": "Водяной знак", "control": "text", "group": "advanced"},
    "enable_fallback": {"label": "Fallback", "control": "toggle", "group": "advanced"},
    "enable_translation": {"label": "Автоперевод промпта", "control": "toggle", "group": "advanced"},
    "generation_type": {"label": "Режим генерации", "control": "combobox", "group": "references", "suggestions": ["TEXT_2_VIDEO", "FIRST_AND_LAST_FRAMES_2_VIDEO", "REFERENCE_2_VIDEO"]},
    "bbox_list": {"label": "Bounding boxes", "control": "json", "group": "advanced"},
}

GROUPS = [
    {"id": "prompt", "title": "Описание"},
    {"id": "references", "title": "Референсы"},
    {"id": "output", "title": "Результат"},
    {"id": "advanced", "title": "Дополнительно", "collapsible": True},
]


def _scenario(scenario_id: str, title: str, visible_fields: list[str], clear_fields: list[str]) -> dict[str, Any]:
    return {"id": scenario_id, "title": title, "visible_fields": visible_fields, "clear_fields": clear_fields}


SEEDANCE_SCENARIOS = [
    _scenario("text", "Текст", [], ["first_frame_url", "last_frame_url", "reference_image_urls", "reference_video_urls", "reference_audio_urls"]),
    _scenario("first_frame", "Первый кадр", ["first_frame_url"], ["last_frame_url", "reference_image_urls", "reference_video_urls", "reference_audio_urls"]),
    _scenario("first_last", "Первый + последний", ["first_frame_url", "last_frame_url"], ["reference_image_urls", "reference_video_urls", "reference_audio_urls"]),
    _scenario("references", "Мультиреференсы", ["reference_image_urls", "reference_video_urls", "reference_audio_urls"], ["first_frame_url", "last_frame_url"]),
]

MODEL_OVERRIDES: dict[str, dict[str, Any]] = {
    "nano-banana-2-lite": {"defaults": {"aspect_ratio": "auto"}},
    "seedream_5_pro": {"defaults": {"aspect_ratio": "1:1", "quality": "high", "output_format": "png"}, "field_overrides": {"image_urls": {"max_items": 10}}},
    "banana_pro": {"defaults": {"aspect_ratio": "auto", "resolution": "1K", "output_format": "png"}, "field_overrides": {"image_input": {"max_items": 8}}},
    "banana_2": {"defaults": {"aspect_ratio": "auto", "resolution": "1K", "output_format": "png"}, "field_overrides": {"image_input": {"max_items": 14}}},
    "seedream_edit": {"defaults": {"aspect_ratio": "1:1", "quality": "high"}, "field_overrides": {"image_urls": {"max_items": 14}}},
    "flux_pro": {"defaults": {"aspect_ratio": "auto", "resolution": "1K"}, "field_overrides": {"input_urls": {"max_items": 16}}},
    "wan_27": {"defaults": {"resolution": "1K", "n": 1, "enable_sequential": False, "thinking_mode": False, "watermark": False}, "field_overrides": {"input_urls": {"max_items": 9}}},
    "grok_imagine_i2i": {"defaults": {"nsfw_checker": False}, "field_overrides": {"image_urls": {"max_items": 1}}},
    "v3_std": {"defaults": {"duration": 5, "aspect_ratio": "16:9", "sound": True, "multi_shots": False}, "field_overrides": {"image_urls": {"label": "Первый / последний кадр", "max_items": 2}}},
    "v3_pro": {"defaults": {"duration": 5, "aspect_ratio": "16:9", "sound": True, "multi_shots": False}, "field_overrides": {"image_urls": {"label": "Первый / последний кадр", "max_items": 2}}},
    "v26_pro": {"defaults": {"duration": 5, "aspect_ratio": "16:9", "cfg_scale": 0.5}},
    "grok_imagine": {"defaults": {"duration": 6, "resolution": "720p", "aspect_ratio": "16:9", "mode": "normal", "nsfw_checker": False}, "field_overrides": {"image_urls": {"max_items": 7}}},
    "grok_imagine_v15": {"defaults": {"duration": 8, "resolution": "480p", "aspect_ratio": "auto", "nsfw_checker": False}, "field_overrides": {"image_urls": {"max_items": 1}}},
    "seedance_2": {"defaults": {"duration": 5, "aspect_ratio": "16:9", "generate_audio": False}, "scenario": {"default": "text", "items": SEEDANCE_SCENARIOS}, "field_overrides": {"reference_image_urls": {"max_items": 9}, "reference_video_urls": {"max_items": 3}, "reference_audio_urls": {"max_items": 1}}},
    "gemini_omni": {"defaults": {"duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}, "field_overrides": {"image_urls": {"max_items": 7}}},
    "veo3_fast": {"defaults": {"duration": 6, "aspect_ratio": "16:9", "enable_fallback": False, "enable_translation": True, "generation_type": "TEXT_2_VIDEO"}, "field_overrides": {"image_urls": {"label": "Кадры / референсы", "max_items": 3}}},
    "motion_control_v26": {"defaults": {"mode": "720p", "character_orientation": "video"}, "field_overrides": {"input_urls": {"label": "Фото персонажа", "max_items": 1, "max_size_mb": 10}, "video_urls": {"label": "Видео движения", "max_items": 1, "max_size_mb": 100}}, "billing_seconds": {"label": "Длительность референс-видео", "min": 3, "max": 30, "required": True}},
    "motion_control_v30": {"defaults": {"mode": "720p", "character_orientation": "video", "background_source": "input_video"}, "field_overrides": {"input_urls": {"label": "Фото персонажа", "max_items": 1, "max_size_mb": 10}, "video_urls": {"label": "Видео движения", "max_items": 1, "max_size_mb": 100}}, "billing_seconds": {"label": "Длительность референс-видео", "min": 3, "max": 30, "required": True}},
    "avatar_std": {"field_overrides": {"image_url": {"label": "Фото аватара", "max_size_mb": 10}, "audio_url": {"label": "Аудио для речи", "max_size_mb": 15}}},
    "avatar_pro": {"field_overrides": {"image_url": {"label": "Фото аватара", "max_size_mb": 10}, "audio_url": {"label": "Аудио для речи", "max_size_mb": 15}}},
}


def build_model_ui_schema(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model["id"])
    known_fields = [str(item) for item in model.get("known_fields", [])]
    required = {str(item) for item in model.get("required_fields", [])}
    override = deepcopy(MODEL_OVERRIDES.get(model_id, {}))
    field_overrides = override.pop("field_overrides", {})

    fields: list[dict[str, Any]] = []
    for name in known_fields:
        base = deepcopy(FIELD_DEFINITIONS.get(name, {}))
        if not base:
            raise ValueError(f"No UI field definition for {model_id}.{name}")
        base.update(field_overrides.get(name, {}))
        base["name"] = name
        base["required"] = name in required
        if name == "duration":
            if model.get("min_seconds") is not None:
                base["min"] = model["min_seconds"]
            if model.get("max_seconds") is not None:
                base["max"] = model["max_seconds"]
        fields.append(base)

    schema: dict[str, Any] = {
        "version": 1,
        "groups": GROUPS,
        "fields": fields,
        "defaults": override.get("defaults", {}),
        "summary_fields": [field["name"] for field in fields if field["name"] != "prompt" and field.get("control") != "json"],
    }
    if "scenario" in override:
        schema["scenario"] = override["scenario"]
    if "billing_seconds" in override:
        schema["billing_seconds"] = override["billing_seconds"]
    elif model.get("price_mode") == "per_second" and "duration" not in known_fields:
        schema["billing_seconds"] = {
            "label": "Длительность для расчёта",
            "min": model.get("min_seconds") or 1,
            "max": model.get("max_seconds") or 600,
            "required": True,
        }
    return schema
