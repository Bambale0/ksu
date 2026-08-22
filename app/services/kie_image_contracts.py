from __future__ import annotations

from copy import deepcopy
from typing import Any


class KieImageContractError(ValueError):
    pass


NANO_LEGACY_RATIOS = {
    "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9", "auto"
}
NANO_PRO_RATIOS = {
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"
}
NANO_2_RATIOS = {
    "1:1", "2:3", "3:2", "1:4", "4:1", "3:4", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "auto"
}
SEEDREAM_RATIOS = {"1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"}
SEEDREAM_3_SIZES = {
    "square",
    "square_hd",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
}
SEEDREAM_4_SIZES = SEEDREAM_3_SIZES | {
    "portrait_3_2",
    "landscape_3_2",
    "landscape_21_9",
}
GPT_15_RATIOS = {"1:1", "2:3", "3:2"}
GPT_2_RATIOS = {
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16",
    "2:1", "1:2", "3:1", "1:3", "21:9", "9:21", "5:4", "4:5",
}
GPT_2_LARGE_BLOCKED_RATIOS = {"5:4", "4:5", "3:1", "1:3", "9:21"}
WAN_RATIOS = {"1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"}
GROK_RATIOS = {"2:3", "3:2", "1:1", "9:16", "16:9"}


# Provider model names used by app/services/model_catalog.py.
IMAGE_MODELS = {
    "google/nano-banana",
    "google/nano-banana-edit",
    "nano-banana-pro",
    "nano-banana-2",
    "nano-banana-2-lite",
    "bytedance/seedream",
    "bytedance/seedream-v4-text-to-image",
    "bytedance/seedream-v4-edit",
    "seedream/4.5-text-to-image",
    "seedream/4.5-edit",
    "seedream/5-lite-text-to-image",
    "seedream/5-lite-image-to-image",
    "seedream/5-pro-text-to-image",
    "seedream/5-pro-image-to-image",
    "seedream/5-pro-layer-decomposition",
    "gpt-image/1.5-text-to-image",
    "gpt-image/1.5-image-to-image",
    "gpt-image-2-text-to-image",
    "gpt-image-2-image-to-image",
    "wan/2-7-image",
    "wan/2-7-image-pro",
    "grok-imagine/text-to-image",
    "grok-imagine/image-to-image",
}


def _enum(data: dict[str, Any], key: str, allowed: set[str]) -> None:
    value = data.get(key)
    if value in (None, ""):
        return
    normalized = str(value)
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise KieImageContractError(f"Unsupported {key}={normalized!r}; allowed: {choices}")


def _bool(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if value is None:
        return
    if not isinstance(value, bool):
        raise KieImageContractError(f"{key} must be a boolean")


def _list_max(data: dict[str, Any], key: str, maximum: int, *, required: bool = False) -> None:
    value = data.get(key)
    if value in (None, ""):
        if required:
            raise KieImageContractError(f"{key} is required")
        return
    if not isinstance(value, list):
        raise KieImageContractError(f"{key} must be an array")
    if required and not value:
        raise KieImageContractError(f"{key} is required")
    if len(value) > maximum:
        raise KieImageContractError(f"{key} accepts at most {maximum} images")


def _int_range(data: dict[str, Any], key: str, minimum: int, maximum: int) -> None:
    value = data.get(key)
    if value in (None, ""):
        return
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise KieImageContractError(f"{key} must be an integer") from exc
    if not minimum <= normalized <= maximum:
        raise KieImageContractError(f"{key} must be between {minimum} and {maximum}")
    data[key] = normalized


def _has_images(data: dict[str, Any]) -> bool:
    for key in ("input_urls", "image_urls", "image_input", "image_url"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value:
            return True
    return False


def _normalize_seedream_4_prompt(data: dict[str, Any]) -> None:
    count = data.get("max_images")
    if count in (None, ""):
        return
    count = int(count)
    prompt = str(data.get("prompt") or "").strip()
    marker = f"Generate exactly {count} images in this set."
    if marker.lower() not in prompt.lower():
        data["prompt"] = f"{prompt}\n\n{marker}" if prompt else marker


def normalize_kie_image_input(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize Kie image inputs against current provider model contracts.

    This runs immediately before createTask. It deliberately leaves unknown/non-image
    models untouched, so video/audio flows keep their existing behavior.
    """

    data = deepcopy(input_data)
    if model not in IMAGE_MODELS:
        return data

    if model in {"google/nano-banana", "google/nano-banana-edit"}:
        _enum(data, "aspect_ratio", NANO_LEGACY_RATIOS)
        _enum(data, "output_format", {"png", "jpeg"})
        if model.endswith("edit"):
            _list_max(data, "image_urls", 10, required=True)
        return data

    if model == "nano-banana-pro":
        _enum(data, "aspect_ratio", NANO_PRO_RATIOS)
        _enum(data, "resolution", {"1K", "2K", "4K"})
        _enum(data, "output_format", {"png", "jpg"})
        _list_max(data, "image_input", 8)
        return data

    if model == "nano-banana-2":
        _enum(data, "aspect_ratio", NANO_2_RATIOS)
        _enum(data, "resolution", {"1K", "2K", "4K"})
        _enum(data, "output_format", {"jpg", "png"})
        _list_max(data, "image_input", 14)
        return data

    if model == "nano-banana-2-lite":
        _enum(data, "aspect_ratio", NANO_2_RATIOS)
        _list_max(data, "image_urls", 10)
        return data

    if model == "bytedance/seedream":
        _enum(data, "image_size", SEEDREAM_3_SIZES)
        return data

    if model in {"bytedance/seedream-v4-text-to-image", "bytedance/seedream-v4-edit"}:
        _enum(data, "image_size", SEEDREAM_4_SIZES)
        _enum(data, "image_resolution", {"1K", "2K", "4K"})
        _int_range(data, "max_images", 1, 6)
        if model.endswith("edit"):
            _list_max(data, "image_urls", 10, required=True)
        _normalize_seedream_4_prompt(data)
        return data

    if model in {"seedream/4.5-text-to-image", "seedream/4.5-edit"}:
        _enum(data, "aspect_ratio", SEEDREAM_RATIOS)
        _enum(data, "quality", {"basic", "high"})
        if model.endswith("edit"):
            _list_max(data, "image_urls", 14, required=True)
        return data

    if model in {"seedream/5-lite-text-to-image", "seedream/5-lite-image-to-image"}:
        _enum(data, "aspect_ratio", SEEDREAM_RATIOS)
        _enum(data, "quality", {"basic", "high", "ultra"})
        _enum(data, "output_format", {"png", "jpeg"})
        if model.endswith("image-to-image"):
            _list_max(data, "image_urls", 14, required=True)
        return data

    if model in {"seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"}:
        _enum(data, "aspect_ratio", SEEDREAM_RATIOS)
        _enum(data, "quality", {"basic", "high"})
        _enum(data, "output_format", {"png", "jpeg"})
        if model.endswith("image-to-image"):
            _list_max(data, "image_urls", 10, required=True)
        return data

    if model == "seedream/5-pro-layer-decomposition":
        _enum(data, "output_format", {"png", "jpeg"})
        return data

    if model in {"gpt-image/1.5-text-to-image", "gpt-image/1.5-image-to-image"}:
        _enum(data, "aspect_ratio", GPT_15_RATIOS)
        _enum(data, "quality", {"medium", "high"})
        if model.endswith("image-to-image"):
            _list_max(data, "input_urls", 16, required=True)
        return data

    if model in {"gpt-image-2-text-to-image", "gpt-image-2-image-to-image"}:
        _enum(data, "aspect_ratio", GPT_2_RATIOS)
        _enum(data, "resolution", {"1K", "2K", "4K"})
        resolution = str(data.get("resolution") or "1K")
        ratio = str(data.get("aspect_ratio") or "auto")
        if resolution in {"2K", "4K"} and ratio in GPT_2_LARGE_BLOCKED_RATIOS:
            raise KieImageContractError(
                f"GPT Image 2 does not support aspect_ratio={ratio} at {resolution}"
            )
        if model.endswith("image-to-image"):
            _list_max(data, "input_urls", 16)
        return data

    if model in {"wan/2-7-image", "wan/2-7-image-pro"}:
        _enum(data, "aspect_ratio", WAN_RATIOS)
        allowed_resolution = {"1K", "2K", "4K"} if model.endswith("-pro") else {"1K", "2K"}
        _enum(data, "resolution", allowed_resolution)
        _list_max(data, "input_urls", 9)
        gallery = bool(data.get("enable_sequential"))
        _int_range(data, "n", 1, 12 if gallery else 4)
        _bool(data, "thinking_mode")
        _bool(data, "watermark")
        _bool(data, "nsfw_checker")
        if (_has_images(data) or gallery) and bool(data.get("thinking_mode")):
            raise KieImageContractError(
                "WAN thinking_mode is available only for a single text-to-image generation"
            )
        if model.endswith("-pro") and _has_images(data) and data.get("resolution") == "4K":
            raise KieImageContractError(
                "WAN 2.7 Pro 4K is available only for text-to-image generation"
            )
        return data

    if model == "grok-imagine/text-to-image":
        _enum(data, "aspect_ratio", GROK_RATIOS)
        _bool(data, "enable_pro")
        _bool(data, "nsfw_checker")
        return data

    if model == "grok-imagine/image-to-image":
        _list_max(data, "image_urls", 1, required=True)
        _bool(data, "nsfw_checker")
        return data

    return data
