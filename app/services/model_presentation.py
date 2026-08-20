from __future__ import annotations

from typing import Any


# Customer-facing names are deliberately separated from provider IDs but remain
# keyed by the exact runtime model id. This is the only presentation map used by
# the Mini App create menu; provider submission never reads these labels.
_PRESENTATION: dict[str, dict[str, str | None]] = {
    # Nano Banana
    "nano-banana": {"title": "Nano Banana", "product_key": "nano-banana", "product_title": "Nano Banana", "family_group": "nano-banana", "family_title": "Nano Banana", "version_label": "Base"},
    "nano-banana-edit": {"title": "Nano Banana Edit", "product_key": "nano-banana", "product_title": "Nano Banana", "family_group": "nano-banana", "family_title": "Nano Banana", "version_label": "Base"},
    "nano-banana-pro": {"title": "Nano Banana Pro", "product_key": "nano-banana-pro", "product_title": "Nano Banana Pro", "family_group": "nano-banana", "family_title": "Nano Banana", "version_label": "Pro"},
    "nano-banana-2": {"title": "Nano Banana 2", "product_key": "nano-banana-2", "product_title": "Nano Banana 2", "family_group": "nano-banana", "family_title": "Nano Banana", "version_label": "2"},
    "nano-banana-2-lite": {"title": "Nano Banana 2 Lite", "product_key": "nano-banana-2-lite", "product_title": "Nano Banana 2 Lite", "family_group": "nano-banana", "family_title": "Nano Banana", "version_label": "2 Lite"},

    # Seedream
    "seedream-3-t2i": {"title": "Seedream 3.0 · Text to Image", "product_key": "seedream-3", "product_title": "Seedream 3.0", "family_group": "seedream", "family_title": "Seedream", "version_label": "3.0"},
    "seedream-4-t2i": {"title": "Seedream 4.0 · Text to Image", "product_key": "seedream-4", "product_title": "Seedream 4.0", "family_group": "seedream", "family_title": "Seedream", "version_label": "4.0"},
    "seedream-4-edit": {"title": "Seedream 4.0 · Edit", "product_key": "seedream-4", "product_title": "Seedream 4.0", "family_group": "seedream", "family_title": "Seedream", "version_label": "4.0"},
    "seedream-4.5-t2i": {"title": "Seedream 4.5 · Text to Image", "product_key": "seedream-4.5", "product_title": "Seedream 4.5", "family_group": "seedream", "family_title": "Seedream", "version_label": "4.5"},
    "seedream-4.5-edit": {"title": "Seedream 4.5 · Edit", "product_key": "seedream-4.5", "product_title": "Seedream 4.5", "family_group": "seedream", "family_title": "Seedream", "version_label": "4.5"},
    "seedream-5-lite-t2i": {"title": "Seedream 5.0 Lite · Text to Image", "product_key": "seedream-5-lite", "product_title": "Seedream 5.0 Lite", "family_group": "seedream", "family_title": "Seedream", "version_label": "5.0 Lite"},
    "seedream-5-lite-i2i": {"title": "Seedream 5.0 Lite · Image to Image", "product_key": "seedream-5-lite", "product_title": "Seedream 5.0 Lite", "family_group": "seedream", "family_title": "Seedream", "version_label": "5.0 Lite"},
    "seedream-5-pro-t2i": {"title": "Seedream 5.0 Pro · Text to Image", "product_key": "seedream-5-pro", "product_title": "Seedream 5.0 Pro", "family_group": "seedream", "family_title": "Seedream", "version_label": "5.0 Pro"},
    "seedream-5-pro-i2i": {"title": "Seedream 5.0 Pro · Image to Image", "product_key": "seedream-5-pro", "product_title": "Seedream 5.0 Pro", "family_group": "seedream", "family_title": "Seedream", "version_label": "5.0 Pro"},
    "seedream-5-pro-layers": {"title": "Seedream 5.0 Pro · Layer Decomposition", "product_key": "seedream-5-pro", "product_title": "Seedream 5.0 Pro", "family_group": "seedream", "family_title": "Seedream", "version_label": "5.0 Pro"},

    # GPT Image
    "gpt-image-1.5-t2i": {"title": "GPT Image 1.5 · Text to Image", "product_key": "gpt-image-1.5", "product_title": "GPT Image 1.5", "family_group": "gpt-image", "family_title": "GPT Image", "version_label": "1.5"},
    "gpt-image-1.5-i2i": {"title": "GPT Image 1.5 · Image to Image", "product_key": "gpt-image-1.5", "product_title": "GPT Image 1.5", "family_group": "gpt-image", "family_title": "GPT Image", "version_label": "1.5"},
    "gpt-image-2-t2i": {"title": "GPT Image 2 · Text to Image", "product_key": "gpt-image-2", "product_title": "GPT Image 2", "family_group": "gpt-image", "family_title": "GPT Image", "version_label": "2"},
    "gpt-image-2-i2i": {"title": "GPT Image 2 · Image to Image", "product_key": "gpt-image-2", "product_title": "GPT Image 2", "family_group": "gpt-image", "family_title": "GPT Image", "version_label": "2"},

    # Wan 2.7
    "wan-2.7-image": {"title": "Wan 2.7", "product_key": "wan-2.7-image", "product_title": "Wan 2.7", "family_group": "wan-image", "family_title": "Wan Image 2.7", "version_label": "Standard"},
    "wan-2.7-image-pro": {"title": "Wan 2.7 Pro", "product_key": "wan-2.7-image-pro", "product_title": "Wan 2.7 Pro", "family_group": "wan-image", "family_title": "Wan Image 2.7", "version_label": "Pro"},
    "wan-2.7-t2v": {"title": "Wan 2.7 · Text to Video", "product_key": "wan-2.7-video", "product_title": "Wan 2.7", "family_group": None, "family_title": "Wan", "version_label": "2.7"},
    "wan-2.7-i2v": {"title": "Wan 2.7 · Image to Video", "product_key": "wan-2.7-video", "product_title": "Wan 2.7", "family_group": None, "family_title": "Wan", "version_label": "2.7"},
    "wan-2.7-video-edit": {"title": "Wan 2.7 · Video Edit", "product_key": "wan-2.7-video", "product_title": "Wan 2.7", "family_group": None, "family_title": "Wan", "version_label": "2.7"},
    "wan-2.7-r2v": {"title": "Wan 2.7 · Reference to Video", "product_key": "wan-2.7-video", "product_title": "Wan 2.7", "family_group": None, "family_title": "Wan", "version_label": "2.7"},

    # Seedance
    "seedance-1.5-pro": {"title": "Seedance 1.5 Pro", "product_key": "seedance-1.5-pro", "product_title": "Seedance 1.5 Pro", "family_group": "seedance", "family_title": "Seedance", "version_label": "1.5 Pro"},
    "seedance-2.0": {"title": "Seedance 2.0", "product_key": "seedance-2.0", "product_title": "Seedance 2.0", "family_group": "seedance", "family_title": "Seedance", "version_label": "2.0"},
    "seedance-2.0-fast": {"title": "Seedance 2.0 Fast", "product_key": "seedance-2.0-fast", "product_title": "Seedance 2.0 Fast", "family_group": "seedance", "family_title": "Seedance", "version_label": "2.0 Fast"},
    "seedance-2.0-mini": {"title": "Seedance 2.0 Mini", "product_key": "seedance-2.0-mini", "product_title": "Seedance 2.0 Mini", "family_group": "seedance", "family_title": "Seedance", "version_label": "2.0 Mini"},
    "seedance-2.5": {"title": "Seedance 2.5", "product_key": "seedance-2.5", "product_title": "Seedance 2.5", "family_group": "seedance", "family_title": "Seedance", "version_label": "2.5"},

    # Kling video / Motion / Avatar are intentionally separate product families.
    "kling-2.5-turbo-pro-t2v": {"title": "Kling 2.5 Turbo Pro · Text to Video", "product_key": "kling-2.5-turbo-pro", "product_title": "Kling 2.5 Turbo Pro", "family_group": "kling-video", "family_title": "Kling Video", "version_label": "2.5 Turbo Pro"},
    "kling-2.5-turbo-pro-i2v": {"title": "Kling 2.5 Turbo Pro · Image to Video", "product_key": "kling-2.5-turbo-pro", "product_title": "Kling 2.5 Turbo Pro", "family_group": "kling-video", "family_title": "Kling Video", "version_label": "2.5 Turbo Pro"},
    "kling-3.0": {"title": "Kling 3.0", "product_key": "kling-3.0", "product_title": "Kling 3.0", "family_group": "kling-video", "family_title": "Kling Video", "version_label": "3.0"},
    "kling-motion-2.6": {"title": "Kling Motion 2.6", "product_key": "kling-motion-2.6", "product_title": "Kling Motion 2.6", "family_group": "kling-motion", "family_title": "Kling Motion", "version_label": "2.6"},
    "kling-motion-3.0": {"title": "Kling Motion 3.0", "product_key": "kling-motion-3.0", "product_title": "Kling Motion 3.0", "family_group": "kling-motion", "family_title": "Kling Motion", "version_label": "3.0"},
    "kling-avatar-standard": {"title": "Kling AI Avatar · Standard", "product_key": "kling-avatar-standard", "product_title": "Kling AI Avatar Standard", "family_group": "kling-avatar", "family_title": "Kling AI Avatar", "version_label": "Standard"},
    "kling-avatar-pro": {"title": "Kling AI Avatar · Pro", "product_key": "kling-avatar-pro", "product_title": "Kling AI Avatar Pro", "family_group": "kling-avatar", "family_title": "Kling AI Avatar", "version_label": "Pro"},

    # Dedicated/singleton video products
    "veo-3.1": {"title": "Veo 3.1", "product_key": "veo-3.1", "product_title": "Veo 3.1", "family_group": None, "family_title": "Veo", "version_label": "3.1"},
    "gemini-omni-video": {"title": "Gemini Omni Video", "product_key": "gemini-omni-video", "product_title": "Gemini Omni Video", "family_group": None, "family_title": "Gemini", "version_label": "Omni Video"},

    # Grok Imagine
    "grok-image-t2i": {"title": "Grok Imagine · Text to Image", "product_key": "grok-image", "product_title": "Grok Imagine", "family_group": None, "family_title": "Grok Imagine", "version_label": "Image"},
    "grok-image-i2i": {"title": "Grok Imagine · Image to Image", "product_key": "grok-image", "product_title": "Grok Imagine", "family_group": None, "family_title": "Grok Imagine", "version_label": "Image"},
    "grok-video-t2v": {"title": "Grok Imagine · Text to Video", "product_key": "grok-video", "product_title": "Grok Imagine Video", "family_group": "grok-video", "family_title": "Grok Imagine Video", "version_label": "Base"},
    "grok-video-i2v": {"title": "Grok Imagine · Image to Video", "product_key": "grok-video", "product_title": "Grok Imagine Video", "family_group": "grok-video", "family_title": "Grok Imagine Video", "version_label": "Base"},
    "grok-video-1.5": {"title": "Grok Imagine Video 1.5 Preview", "product_key": "grok-video-1.5", "product_title": "Grok Imagine Video 1.5 Preview", "family_group": "grok-video", "family_title": "Grok Imagine Video", "version_label": "1.5 Preview"},
    "grok-video-upscale": {"title": "Grok Imagine · Video Upscale", "product_key": "grok-video-upscale", "product_title": "Grok Imagine Video Upscale", "family_group": None, "family_title": "Grok Imagine", "version_label": "Upscale"},
    "grok-video-extend": {"title": "Grok Imagine · Video Extend", "product_key": "grok-video-extend", "product_title": "Grok Imagine Video Extend", "family_group": None, "family_title": "Grok Imagine", "version_label": "Extend"},
}


def presentation_for(model: dict[str, Any]) -> dict[str, str | None]:
    model_id = str(model.get("id") or "")
    configured = _PRESENTATION.get(model_id)
    if configured is not None:
        return dict(configured)
    title = str(model.get("title") or model_id or "ROXY")
    family = str(model.get("family") or "ROXY")
    return {
        "title": title,
        "product_key": model_id,
        "product_title": title,
        "family_group": None,
        "family_title": family,
        "version_label": title,
    }


def public_model_title(model_id: str, fallback: str) -> str:
    return str(_PRESENTATION.get(model_id, {}).get("title") or fallback)


def product_key_for(model_id: str) -> str:
    return str(_PRESENTATION.get(model_id, {}).get("product_key") or model_id)


def music_model_title(provider_model: str) -> str:
    value = str(provider_model or "").strip()
    labels = {
        "V5_5": "Suno V5.5",
        "V5": "Suno V5",
        "V4_5": "Suno V4.5",
        "V4": "Suno V4",
    }
    base = labels.get(value.upper(), f"Suno {value}" if value else "Suno")
    return f"{base} · Music"
