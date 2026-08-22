from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.model_routing import PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS
from app.services.model_ui import build_model_ui_schema

SEEDANCE_MODELS = {
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
}

REFERENCE_FIELD_NAMES = {
    "image_urls",
    "input_urls",
    "image_input",
    "image_url",
    "first_frame_url",
    "last_frame_url",
    "first_frame",
    "reference_image",
    "reference_image_urls",
    "video_urls",
    "video_url",
    "first_clip_url",
    "reference_video",
    "reference_video_urls",
}

NANO_LEGACY_RATIOS = ["auto", "1:1", "16:9", "9:16", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"]
NANO_PRO_RATIOS = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
NANO_2_RATIOS = ["auto", "1:1", "2:3", "3:2", "1:4", "4:1", "3:4", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9"]
SEEDREAM_RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
SEEDREAM_3_SIZES = ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
SEEDREAM_4_SIZES = [*SEEDREAM_3_SIZES, "portrait_3_2", "landscape_3_2", "landscape_21_9"]
GPT_15_RATIOS = ["1:1", "2:3", "3:2"]
GPT_2_RATIOS = ["auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21", "5:4", "4:5"]
WAN_IMAGE_RATIOS = ["1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"]
WAN_VIDEO_RATIOS = ["16:9", "9:16", "1:1"]
GROK_IMAGE_RATIOS = ["2:3", "3:2", "1:1", "9:16", "16:9"]
GROK_VIDEO_RATIOS = ["16:9", "9:16", "1:1", "2:3", "3:2"]

# KIE does not expose one universal duration contract. Keep this map
# intentionally model-specific so the Mini App never falls back to a free
# number input such as 51015 seconds. Values are based on the current KIE
# model pages: examples are used where the page exposes only an example value;
# documented ranges are expanded for user-facing select controls.
KIE_DURATION_OPTIONS: dict[str, list[int]] = {
    "wan-2.7-t2v": [5],
    "wan-2.7-i2v": [5],
    "wan-2.7-r2v": [5],
    "wan-2.7-video-edit": [0],
    "seedance-2.0": [5, 10, 15],
    "seedance-2.0-fast": [5, 10, 15],
    "seedance-2.0-mini": [5, 10, 15],
    "seedance-2.5": [5, 10, 15],
    "seedance-1.5-pro": [8],
    "kling-3.0": list(range(3, 16)),
    "grok-video-t2v": [6],
    "grok-video-i2v": [6],
    "grok-video-1.5": [8],
    "gemini-omni-video": [4],
}

MODEL_FIELD_SUGGESTIONS: dict[str, dict[str, list[str]]] = {
    "nano-banana": {"aspect_ratio": NANO_LEGACY_RATIOS, "output_format": ["png", "jpeg"]},
    "nano-banana-edit": {"aspect_ratio": NANO_LEGACY_RATIOS, "output_format": ["png", "jpeg"]},
    "nano-banana-pro": {"aspect_ratio": NANO_PRO_RATIOS, "resolution": ["1K", "2K", "4K"], "output_format": ["png", "jpg"]},
    "nano-banana-2": {"aspect_ratio": NANO_2_RATIOS, "resolution": ["1K", "2K", "4K"], "output_format": ["png", "jpg"]},
    "nano-banana-2-lite": {"aspect_ratio": NANO_2_RATIOS},
    "seedream-3-t2i": {"image_size": SEEDREAM_3_SIZES},
    "seedream-4-t2i": {"image_size": SEEDREAM_4_SIZES, "image_resolution": ["1K", "2K", "4K"]},
    "seedream-4-edit": {"image_size": SEEDREAM_4_SIZES, "image_resolution": ["1K", "2K", "4K"]},
    "seedream-4.5-t2i": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high"]},
    "seedream-4.5-edit": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high"]},
    "seedream-5-lite-t2i": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high", "ultra"], "output_format": ["png", "jpeg"]},
    "seedream-5-lite-i2i": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high", "ultra"], "output_format": ["png", "jpeg"]},
    "seedream-5-pro-t2i": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high"], "output_format": ["png", "jpeg"]},
    "seedream-5-pro-i2i": {"aspect_ratio": SEEDREAM_RATIOS, "quality": ["basic", "high"], "output_format": ["png", "jpeg"]},
    "seedream-5-pro-layers": {"output_format": ["png", "jpeg"]},
    "gpt-image-1.5-t2i": {"aspect_ratio": GPT_15_RATIOS, "quality": ["medium", "high"]},
    "gpt-image-1.5-i2i": {"aspect_ratio": GPT_15_RATIOS, "quality": ["medium", "high"]},
    "gpt-image-2-t2i": {"aspect_ratio": GPT_2_RATIOS},
    "gpt-image-2-i2i": {"aspect_ratio": GPT_2_RATIOS},
    "wan-2.7-image": {"aspect_ratio": WAN_IMAGE_RATIOS, "resolution": ["1K", "2K"]},
    "wan-2.7-image-pro": {"aspect_ratio": WAN_IMAGE_RATIOS, "resolution": ["1K", "2K", "4K"]},
    "wan-2.7-t2v": {"ratio": WAN_VIDEO_RATIOS, "resolution": ["720p", "1080p"]},
    "wan-2.7-i2v": {"aspect_ratio": WAN_VIDEO_RATIOS, "resolution": ["720p", "1080p"]},
    "wan-2.7-video-edit": {"aspect_ratio": WAN_VIDEO_RATIOS, "resolution": ["720p", "1080p"]},
    "wan-2.7-r2v": {"aspect_ratio": WAN_VIDEO_RATIOS, "resolution": ["720p", "1080p"]},
    "seedance-1.5-pro": {"aspect_ratio": ["16:9", "9:16", "1:1"], "resolution": ["480p", "720p", "1080p"]},
    "seedance-2.0": {"aspect_ratio": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"], "resolution": ["480p", "720p"]},
    "seedance-2.0-fast": {"aspect_ratio": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"], "resolution": ["480p", "720p"]},
    "seedance-2.0-mini": {"aspect_ratio": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"], "resolution": ["480p", "720p"]},
    "seedance-2.5": {"resolution": ["480p", "720p"], "aspect_ratio": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"], "output_format": ["mp4", "mov"]},
    "kling-3.0": {"mode": ["std", "pro", "4K"], "aspect_ratio": ["16:9", "9:16", "1:1"]},
    "kling-motion-2.6": {"mode": ["720p", "1080p"], "character_orientation": ["image", "video"]},
    "kling-motion-3.0": {"mode": ["720p", "1080p"], "character_orientation": ["image", "video"], "background_source": ["input_video", "input_image"]},
    "veo-3.1": {"veo_model": ["veo3", "veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"], "aspect_ratio": ["16:9", "9:16", "Auto"], "generation_type": ["TEXT_2_VIDEO", "FIRST_AND_LAST_FRAMES_2_VIDEO", "REFERENCE_2_VIDEO"]},
    "grok-image-t2i": {"aspect_ratio": GROK_IMAGE_RATIOS},
    "grok-video-t2v": {"aspect_ratio": GROK_VIDEO_RATIOS, "mode": ["normal"], "resolution": ["480p"]},
    "grok-video-i2v": {"aspect_ratio": GROK_VIDEO_RATIOS, "mode": ["normal"], "resolution": ["480p"]},
    "grok-video-1.5": {"aspect_ratio": GROK_VIDEO_RATIOS, "resolution": ["480p"]},
}

MODEL_DEFAULTS: dict[str, dict[str, Any]] = {
    "nano-banana": {"aspect_ratio": "1:1", "output_format": "png"},
    "nano-banana-edit": {"aspect_ratio": "1:1", "output_format": "png"},
    "nano-banana-pro": {"aspect_ratio": "1:1", "resolution": "1K", "output_format": "png"},
    "nano-banana-2": {"aspect_ratio": "auto", "resolution": "1K", "output_format": "png"},
    "nano-banana-2-lite": {"aspect_ratio": "auto"},
    "seedream-3-t2i": {"image_size": "square_hd"},
    "seedream-4-t2i": {"image_size": "square_hd", "image_resolution": "1K", "max_images": 1},
    "seedream-4-edit": {"image_size": "square_hd", "image_resolution": "1K", "max_images": 1},
    "seedream-4.5-t2i": {"aspect_ratio": "1:1", "quality": "basic"},
    "seedream-4.5-edit": {"aspect_ratio": "1:1", "quality": "basic"},
    "seedream-5-lite-t2i": {"aspect_ratio": "1:1", "quality": "basic", "output_format": "png"},
    "seedream-5-lite-i2i": {"aspect_ratio": "1:1", "quality": "basic", "output_format": "png"},
    "seedream-5-pro-t2i": {"aspect_ratio": "1:1", "quality": "basic", "output_format": "png"},
    "seedream-5-pro-i2i": {"aspect_ratio": "1:1", "quality": "basic", "output_format": "png"},
    "gpt-image-1.5-t2i": {"aspect_ratio": "1:1", "quality": "medium"},
    "gpt-image-1.5-i2i": {"aspect_ratio": "1:1", "quality": "medium"},
    "gpt-image-2-t2i": {"aspect_ratio": "auto"},
    "gpt-image-2-i2i": {"aspect_ratio": "auto"},
    "wan-2.7-image": {"aspect_ratio": "1:1", "resolution": "1K", "n": 1, "thinking_mode": False, "watermark": False},
    "wan-2.7-image-pro": {"aspect_ratio": "1:1", "resolution": "1K", "n": 1, "thinking_mode": False, "watermark": False},
    "wan-2.7-t2v": {"ratio": "16:9", "resolution": "1080p", "duration": 5},
    "wan-2.7-i2v": {"aspect_ratio": "16:9", "resolution": "1080p", "duration": 5},
    "wan-2.7-video-edit": {"aspect_ratio": "16:9", "resolution": "1080p", "duration": 0},
    "wan-2.7-r2v": {"aspect_ratio": "16:9", "resolution": "1080p", "duration": 5},
    "seedance-1.5-pro": {"aspect_ratio": "16:9", "resolution": "720p", "duration": 8, "generate_audio": False, "fixed_lens": False, "nsfw_checker": True},
    "seedance-2.0": {"resolution": "720p", "aspect_ratio": "adaptive", "duration": 5, "generate_audio": False, "return_last_frame": False, "web_search": False},
    "seedance-2.0-fast": {"resolution": "720p", "aspect_ratio": "adaptive", "duration": 5, "generate_audio": False, "return_last_frame": False, "web_search": False},
    "seedance-2.0-mini": {"resolution": "720p", "aspect_ratio": "adaptive", "duration": 5, "generate_audio": False, "return_last_frame": False, "web_search": False},
    "seedance-2.5": {"resolution": "720p", "aspect_ratio": "adaptive", "duration": 5, "output_format": "mp4", "generate_audio": False, "return_last_frame": False, "web_search": False},
    "kling-3.0": {"mode": "std", "aspect_ratio": "16:9", "duration": 5, "sound": False, "multi_shots": False},
    "kling-motion-2.6": {"mode": "720p", "character_orientation": "image"},
    "kling-motion-3.0": {"mode": "720p", "character_orientation": "image", "background_source": "input_video"},
    "veo-3.1": {"veo_model": "veo3_fast", "aspect_ratio": "Auto", "generation_type": "TEXT_2_VIDEO", "enable_fallback": True, "enable_translation": True},
    "grok-image-t2i": {"aspect_ratio": "1:1"},
    "grok-video-t2v": {"aspect_ratio": "16:9", "mode": "normal", "resolution": "480p", "duration": 6},
    "grok-video-i2v": {"aspect_ratio": "16:9", "mode": "normal", "resolution": "480p", "duration": 6},
    "grok-video-1.5": {"aspect_ratio": "16:9", "resolution": "480p", "duration": 8},
}


def _field(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    for field in schema.get("fields", []):
        if field.get("name") == name:
            return field
    return None


def _patch_field(schema: dict[str, Any], name: str, **updates: Any) -> None:
    field = _field(schema, name)
    if field is not None:
        field.update(updates)


def build_public_model_ui_schema(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id") or "")
    schema = deepcopy(build_model_ui_schema(model))

    defaults = deepcopy(MODEL_DEFAULTS.get(model_id, {}))
    for name, suggestions in MODEL_FIELD_SUGGESTIONS.get(model_id, {}).items():
        _patch_field(schema, name, suggestions=suggestions, control="combobox")
    if defaults:
        schema["defaults"] = {
            **schema.get("defaults", {}),
            **{name: value for name, value in defaults.items() if _field(schema, name)},
        }

    duration_options = KIE_DURATION_OPTIONS.get(model_id)
    if duration_options and _field(schema, "duration") is not None:
        _patch_field(schema, "duration", control="combobox", suggestions=duration_options)

    if model_id in PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS:
        for field in schema.get("fields", []):
            if field.get("name") in REFERENCE_FIELD_NAMES:
                field["required"] = False

    scenario = schema.get("scenario")
    if isinstance(scenario, dict):
        for item in scenario.get("items", []):
            visible = [str(name) for name in item.get("visible_fields", [])]
            scenario_id = str(item.get("id") or "")
            if model_id in SEEDANCE_MODELS:
                if scenario_id == "references":
                    item["required_any"] = visible
                elif scenario_id != "text":
                    item["required_fields"] = visible
            elif model_id == "wan-2.7-i2v":
                item["required_fields"] = visible

    if model_id == "seedance-2.5":
        _patch_field(schema, "reference_image_urls", max_items=30, max_size_mb=30)
        _patch_field(schema, "reference_video_urls", max_items=10, max_size_mb=200)
        _patch_field(schema, "reference_audio_urls", max_items=10, max_size_mb=15)

    if model_id in {"kling-motion-2.6", "kling-motion-3.0"}:
        _patch_field(schema, "input_urls", max_size_mb=10, max_items=1)
        _patch_field(schema, "video_urls", max_size_mb=100, max_items=1)

    if model_id == "kling-3.0":
        _patch_field(schema, "image_urls", label="Первый / последний кадр", max_items=2, max_size_mb=10)
        _patch_field(schema, "mode", label="Качество", control="combobox", group="output")
        _patch_field(schema, "sound", label="Нативный звук", control="toggle", group="output")
        _patch_field(schema, "multi_shots", label="Multi-shot", control="toggle", group="output")
        _patch_field(schema, "multi_prompt", label="Кадры multi-shot", control="json", group="advanced", placeholder='[{"prompt":"...","duration":3}]')
        _patch_field(schema, "kling_elements", label="Element references", control="json", group="references", placeholder='[{"name":"hero","description":"...","element_input_urls":["...","..."]}]')

    if model_id == "veo-3.1":
        _patch_field(schema, "image_urls", label="Кадры / референсы", max_items=3)
        _patch_field(schema, "veo_model", label="Версия Veo", control="combobox", group="output")
        _patch_field(schema, "watermark_text", label="Водяной знак", control="text", group="advanced")
        _patch_field(schema, "enable_fallback", label="Fallback", control="toggle", group="advanced")
        _patch_field(schema, "enable_translation", label="Автоперевод промпта", control="toggle", group="advanced")
        _patch_field(schema, "generation_type", label="Режим генерации", control="combobox", group="references")

    if model_id == "gemini-omni-video":
        _patch_field(schema, "image_urls", label="Изображения", max_items=7)
        _patch_field(schema, "audio_ids", label="Gemini Omni audio IDs", control="json", group="references", placeholder='["audio_id"]')
        _patch_field(schema, "video_list", label="Видео-референс", control="json", group="references", placeholder='[{"url":"https://...","start":0,"ends":10}]')
        _patch_field(schema, "character_ids", label="Character IDs", control="json", group="references", placeholder='["character_id"]')

    return schema
