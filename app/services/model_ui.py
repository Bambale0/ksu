from __future__ import annotations

from copy import deepcopy
from typing import Any


FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "prompt": {
        "label": "Промпт",
        "control": "textarea",
        "group": "prompt",
        "placeholder": "Опишите желаемый результат",
    },
    "negative_prompt": {
        "label": "Негативный промпт",
        "control": "textarea",
        "group": "advanced",
        "placeholder": "Что исключить из результата",
    },
    "aspect_ratio": {
        "label": "Соотношение сторон",
        "control": "combobox",
        "group": "output",
        "suggestions": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
    },
    "ratio": {
        "label": "Соотношение сторон",
        "control": "combobox",
        "group": "output",
        "suggestions": ["16:9", "9:16", "1:1"],
    },
    "resolution": {
        "label": "Разрешение",
        "control": "combobox",
        "group": "output",
        "suggestions": ["480p", "720p", "1080p", "1K", "2K", "4K"],
    },
    "image_resolution": {
        "label": "Разрешение изображения",
        "control": "combobox",
        "group": "output",
        "suggestions": ["1K", "2K", "4K"],
    },
    "image_size": {
        "label": "Размер изображения",
        "control": "combobox",
        "group": "output",
        "suggestions": ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
    },
    "size": {
        "label": "Размер",
        "control": "text",
        "group": "output",
    },
    "quality": {
        "label": "Качество",
        "control": "combobox",
        "group": "output",
        "suggestions": ["auto", "standard", "high", "low", "1K", "2K", "4K"],
    },
    "output_format": {
        "label": "Формат результата",
        "control": "combobox",
        "group": "output",
        "suggestions": ["png", "jpeg", "webp"],
    },
    "duration": {
        "label": "Длительность",
        "control": "number",
        "group": "output",
        "step": 1,
        "suffix": "с",
    },
    "seed": {
        "label": "Seed",
        "control": "number",
        "group": "advanced",
        "step": 1,
        "min": 0,
        "placeholder": "Случайный",
    },
    "guidance_scale": {
        "label": "Guidance scale",
        "control": "number",
        "group": "advanced",
        "step": 0.1,
    },
    "cfg_scale": {
        "label": "CFG scale",
        "control": "number",
        "group": "advanced",
        "step": 0.1,
    },
    "n": {
        "label": "Количество вариантов",
        "control": "number",
        "group": "output",
        "step": 1,
        "min": 1,
    },
    "max_images": {
        "label": "Количество изображений",
        "control": "number",
        "group": "output",
        "step": 1,
        "min": 1,
    },
    "enable_sequential": {
        "label": "Последовательная генерация",
        "control": "toggle",
        "group": "advanced",
    },
    "thinking_mode": {
        "label": "Thinking mode",
        "control": "toggle",
        "group": "advanced",
    },
    "watermark": {
        "label": "Водяной знак",
        "control": "toggle",
        "group": "advanced",
    },
    "prompt_extend": {
        "label": "Авторасширение промпта",
        "control": "toggle",
        "group": "advanced",
    },
    "nsfw_checker": {
        "label": "NSFW-проверка",
        "control": "toggle",
        "group": "advanced",
    },
    "generate_audio": {
        "label": "Сгенерировать звук",
        "control": "toggle",
        "group": "output",
    },
    "return_last_frame": {
        "label": "Вернуть последний кадр",
        "control": "toggle",
        "group": "advanced",
    },
    "fixed_lens": {
        "label": "Зафиксировать камеру",
        "control": "toggle",
        "group": "advanced",
    },
    "web_search": {
        "label": "Web search",
        "control": "toggle",
        "group": "advanced",
    },
    "input_urls": {
        "label": "Референсы",
        "control": "files",
        "group": "references",
        "accept": "image/*",
    },
    "image_urls": {
        "label": "Изображения",
        "control": "files",
        "group": "references",
        "accept": "image/*",
    },
    "image_input": {
        "label": "Изображения",
        "control": "files",
        "group": "references",
        "accept": "image/*",
    },
    "image_url": {
        "label": "Изображение",
        "control": "file",
        "group": "references",
        "accept": "image/*",
    },
    "first_frame_url": {
        "label": "Первый кадр",
        "control": "file",
        "group": "references",
        "accept": "image/*",
    },
    "last_frame_url": {
        "label": "Последний кадр",
        "control": "file",
        "group": "references",
        "accept": "image/*",
    },
    "first_clip_url": {
        "label": "Исходный клип",
        "control": "file",
        "group": "references",
        "accept": "video/*",
    },
    "video_url": {
        "label": "Видео",
        "control": "file",
        "group": "references",
        "accept": "video/*",
    },
    "video_urls": {
        "label": "Видео-референсы",
        "control": "files",
        "group": "references",
        "accept": "video/*",
    },
    "audio_url": {
        "label": "Аудио",
        "control": "file",
        "group": "references",
        "accept": "audio/*",
    },
    "driving_audio_url": {
        "label": "Управляющее аудио",
        "control": "file",
        "group": "references",
        "accept": "audio/*",
    },
    "reference_image": {
        "label": "Референс-изображение",
        "control": "file",
        "group": "references",
        "accept": "image/*",
    },
    "reference_video": {
        "label": "Референс-видео",
        "control": "file",
        "group": "references",
        "accept": "video/*",
    },
    "reference_voice": {
        "label": "Референс-голос",
        "control": "file",
        "group": "references",
        "accept": "audio/*",
    },
    "reference_image_urls": {
        "label": "Референс-изображения",
        "control": "files",
        "group": "references",
        "accept": "image/*",
    },
    "reference_video_urls": {
        "label": "Референс-видео",
        "control": "files",
        "group": "references",
        "accept": "video/*",
    },
    "reference_audio_urls": {
        "label": "Референс-аудио",
        "control": "files",
        "group": "references",
        "accept": "audio/*",
    },
    "first_frame": {
        "label": "Первый кадр",
        "control": "file",
        "group": "references",
        "accept": "image/*",
    },
    "mode": {
        "label": "Режим",
        "control": "combobox",
        "group": "output",
        "suggestions": ["standard", "pro", "720p", "1080p"],
    },
    "character_orientation": {
        "label": "Ориентация персонажа",
        "control": "combobox",
        "group": "output",
        "suggestions": ["image", "video"],
    },
    "background_source": {
        "label": "Источник фона",
        "control": "combobox",
        "group": "output",
        "suggestions": ["input_video", "input_image"],
    },
    "task_id": {
        "label": "Исходная Kie-задача",
        "control": "text",
        "group": "references",
        "placeholder": "task_...",
    },
    "extend_at": {
        "label": "Точка расширения",
        "control": "combobox",
        "group": "output",
        "suggestions": ["end", "start"],
    },
    "extend_times": {
        "label": "Количество расширений",
        "control": "number",
        "group": "output",
        "step": 1,
        "min": 1,
    },
    "bbox_list": {
        "label": "Bounding boxes",
        "control": "json",
        "group": "advanced",
    },
    "audio_setting": {
        "label": "Настройки аудио",
        "control": "json",
        "group": "advanced",
    },
}

GROUPS = [
    {"id": "prompt", "title": "Описание"},
    {"id": "references", "title": "Референсы"},
    {"id": "output", "title": "Результат"},
    {"id": "advanced", "title": "Дополнительно", "collapsible": True},
]


def _scenario(
    scenario_id: str,
    title: str,
    visible_fields: list[str],
    clear_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "title": title,
        "visible_fields": visible_fields,
        "clear_fields": clear_fields,
    }


SEEDANCE_SCENARIOS = [
    _scenario(
        "text",
        "Текст",
        [],
        [
            "reference_image_urls",
            "reference_video_urls",
            "reference_audio_urls",
        ],
    ),
    _scenario(
        "references",
        "Мультиреференсы",
        ["reference_image_urls", "reference_video_urls", "reference_audio_urls"],
        [],
    ),
]

SEEDANCE_FIELD_OVERRIDES: dict[str, dict[str, Any]] = {}

WAN_I2V_SCENARIOS = [
    _scenario(
        "first_frame",
        "Первый кадр",
        ["first_frame_url"],
        ["last_frame_url", "first_clip_url"],
    ),
    _scenario(
        "first_last",
        "Первый + последний",
        ["first_frame_url", "last_frame_url"],
        ["first_clip_url"],
    ),
    _scenario(
        "continuation",
        "Продолжить видео",
        ["first_clip_url"],
        ["first_frame_url", "last_frame_url"],
    ),
]

MODEL_OVERRIDES: dict[str, dict[str, Any]] = {
    "nano-banana": {
        "defaults": {"aspect_ratio": "1:1", "output_format": "png"},
    },
    "nano-banana-2": {
        "defaults": {"aspect_ratio": "auto", "resolution": "1K", "output_format": "png"},
    },
    "seedream-4-t2i": {
        "defaults": {"image_size": "square_hd", "image_resolution": "1K", "max_images": 1},
    },
    "wan-2.7-i2v": {
        "scenario": {"default": "first_frame", "items": WAN_I2V_SCENARIOS},
    },
    "seedance-2.0": {
        "scenario": {"default": "text", "items": SEEDANCE_SCENARIOS},
        "field_overrides": SEEDANCE_FIELD_OVERRIDES,
    },
    "seedance-2.0-fast": {
        "scenario": {"default": "text", "items": SEEDANCE_SCENARIOS},
        "field_overrides": SEEDANCE_FIELD_OVERRIDES,
    },
    "seedance-2.0-mini": {
        "scenario": {"default": "text", "items": SEEDANCE_SCENARIOS},
        "field_overrides": SEEDANCE_FIELD_OVERRIDES,
    },
    "seedance-2.5": {
        "scenario": {"default": "text", "items": SEEDANCE_SCENARIOS},
        "field_overrides": SEEDANCE_FIELD_OVERRIDES,
    },
    "kling-motion-2.6": {
        "field_overrides": {
            "input_urls": {"label": "Фото персонажа", "max_items": 1},
            "video_urls": {"label": "Видео движения", "max_items": 1},
        },
        "billing_seconds": {
            "label": "Длительность референс-видео",
            "min": 3,
            "max": 30,
            "required": True,
        },
    },
    "kling-motion-3.0": {
        "field_overrides": {
            "input_urls": {"label": "Фото персонажа", "max_items": 1},
            "video_urls": {"label": "Видео движения", "max_items": 1},
        },
        "billing_seconds": {
            "label": "Длительность референс-видео",
            "min": 3,
            "max": 30,
            "required": True,
        },
    },
    "grok-video-extend": {
        "billing_seconds": {
            "label": "Оплачиваемая длина расширения",
            "min": 1,
            "max": 60,
            "required": True,
        },
    },
    "grok-video-upscale": {
        "hide_prompt": True,
    },
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
            base = {
                "label": name.replace("_", " ").title(),
                "control": "text",
                "group": "advanced",
            }
        base.update(field_overrides.get(name, {}))
        base["name"] = name
        base["required"] = name in required
        if name == "duration":
            if model.get("min_seconds") is not None:
                base["min"] = model["min_seconds"]
            if model.get("max_seconds") is not None:
                base["max"] = model["max_seconds"]
        fields.append(base)

    hide_prompt = bool(override.get("hide_prompt", False))
    if hide_prompt:
        fields = [field for field in fields if field["name"] != "prompt"]

    schema: dict[str, Any] = {
        "version": 1,
        "groups": GROUPS,
        "fields": fields,
        "defaults": override.get("defaults", {}),
        "summary_fields": [
            field["name"]
            for field in fields
            if field["name"] != "prompt" and field.get("control") != "json"
        ],
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
