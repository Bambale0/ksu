from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.model_catalog import ModelCatalog, ModelSpec, UnknownModelError

IMAGE_REFERENCE_FIELDS = (
    "image_urls",
    "input_urls",
    "image_input",
    "image_url",
    "first_frame_url",
    "last_frame_url",
    "first_frame",
    "reference_image",
    "reference_image_urls",
)
VIDEO_REFERENCE_FIELDS = (
    "video_urls",
    "video_url",
    "first_clip_url",
    "reference_video",
    "reference_video_urls",
)

# One customer-facing product can have two callable provider contracts. The Mini
# App may send either side of the pair; this router picks the executable contract
# from the actual payload instead of making the user choose "T2I"/"I2I" names.
AUTO_ROUTE_PAIRS: dict[str, dict[str, str]] = {
    "nano-banana": {"text": "nano-banana", "reference": "nano-banana-edit"},
    "nano-banana-edit": {"text": "nano-banana", "reference": "nano-banana-edit"},
    "seedream-4-t2i": {"text": "seedream-4-t2i", "reference": "seedream-4-edit"},
    "seedream-4-edit": {"text": "seedream-4-t2i", "reference": "seedream-4-edit"},
    "seedream-4.5-t2i": {"text": "seedream-4.5-t2i", "reference": "seedream-4.5-edit"},
    "seedream-4.5-edit": {"text": "seedream-4.5-t2i", "reference": "seedream-4.5-edit"},
    "seedream-5-lite-t2i": {"text": "seedream-5-lite-t2i", "reference": "seedream-5-lite-i2i"},
    "seedream-5-lite-i2i": {"text": "seedream-5-lite-t2i", "reference": "seedream-5-lite-i2i"},
    "seedream-5-pro-t2i": {"text": "seedream-5-pro-t2i", "reference": "seedream-5-pro-i2i"},
    "seedream-5-pro-i2i": {"text": "seedream-5-pro-t2i", "reference": "seedream-5-pro-i2i"},
    "gpt-image-1.5-t2i": {"text": "gpt-image-1.5-t2i", "reference": "gpt-image-1.5-i2i"},
    "gpt-image-1.5-i2i": {"text": "gpt-image-1.5-t2i", "reference": "gpt-image-1.5-i2i"},
    "gpt-image-2-t2i": {"text": "gpt-image-2-t2i", "reference": "gpt-image-2-i2i"},
    "gpt-image-2-i2i": {"text": "gpt-image-2-t2i", "reference": "gpt-image-2-i2i"},
    "grok-image-t2i": {"text": "grok-image-t2i", "reference": "grok-image-i2i"},
    "grok-image-i2i": {"text": "grok-image-t2i", "reference": "grok-image-i2i"},
    "wan-2.7-t2v": {"text": "wan-2.7-t2v", "reference": "wan-2.7-i2v"},
    "wan-2.7-i2v": {"text": "wan-2.7-t2v", "reference": "wan-2.7-i2v"},
    "grok-video-t2v": {"text": "grok-video-t2v", "reference": "grok-video-i2v"},
    "grok-video-i2v": {"text": "grok-video-t2v", "reference": "grok-video-i2v"},
    "kling-2.5-turbo-pro-t2v": {"text": "kling-2.5-turbo-pro-t2v", "reference": "kling-2.5-turbo-pro-i2v"},
    "kling-2.5-turbo-pro-i2v": {"text": "kling-2.5-turbo-pro-t2v", "reference": "kling-2.5-turbo-pro-i2v"},
}

PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS = frozenset(
    route["reference"] for route in AUTO_ROUTE_PAIRS.values()
)
AUTO_ROUTE_TARGET_IDS = frozenset(
    model_id for route in AUTO_ROUTE_PAIRS.values() for model_id in route.values()
)


@dataclass(frozen=True, slots=True)
class RoutedModelRequest:
    requested_model_id: str
    model_id: str
    spec: ModelSpec
    parameters: dict[str, Any]
    mode: str
    switched: bool


def _non_empty(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if _non_empty(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if _non_empty(item)]
    return [str(value)]


def image_references(parameters: dict[str, Any], input_url: str | None = None) -> list[str]:
    refs: list[str] = []
    for field in IMAGE_REFERENCE_FIELDS:
        refs.extend(_as_list(parameters.get(field)))
    if input_url:
        refs.append(str(input_url))
    return list(dict.fromkeys(refs))


def video_references(parameters: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in VIDEO_REFERENCE_FIELDS:
        refs.extend(_as_list(parameters.get(field)))
    return list(dict.fromkeys(refs))


def has_references(parameters: dict[str, Any], input_url: str | None = None) -> bool:
    return bool(image_references(parameters, input_url) or video_references(parameters))


def _available(model_id: str) -> bool:
    try:
        ModelCatalog.get(model_id)
    except UnknownModelError:
        return False
    return True


def _select_model_id(requested_model_id: str, parameters: dict[str, Any], input_url: str | None) -> str:
    route = AUTO_ROUTE_PAIRS.get(requested_model_id)
    if not route:
        return requested_model_id
    target = route["reference"] if has_references(parameters, input_url) else route["text"]
    return target if _available(target) else requested_model_id


def _apply_reference_aliases(spec: ModelSpec, parameters: dict[str, Any], input_url: str | None) -> dict[str, Any]:
    normalized = dict(parameters)
    image_refs = image_references(parameters, input_url)
    video_refs = video_references(parameters)
    fields = set(spec.known_fields)

    if image_refs:
        if "image_urls" in fields:
            normalized.setdefault("image_urls", image_refs)
        if "input_urls" in fields:
            normalized.setdefault("input_urls", image_refs)
        if "image_input" in fields:
            normalized.setdefault("image_input", image_refs)
        if "reference_image_urls" in fields:
            normalized.setdefault("reference_image_urls", image_refs)
        if "first_frame_url" in fields:
            normalized.setdefault("first_frame_url", image_refs[0])
        if "image_url" in fields:
            normalized.setdefault("image_url", image_refs[0])
        if "first_frame" in fields:
            normalized.setdefault("first_frame", image_refs[0])
        if "reference_image" in fields:
            normalized.setdefault("reference_image", image_refs[0])

    if video_refs:
        if "video_urls" in fields:
            normalized.setdefault("video_urls", video_refs)
        if "reference_video_urls" in fields:
            normalized.setdefault("reference_video_urls", video_refs)
        if "video_url" in fields:
            normalized.setdefault("video_url", video_refs[0])
        if "first_clip_url" in fields:
            normalized.setdefault("first_clip_url", video_refs[0])
        if "reference_video" in fields:
            normalized.setdefault("reference_video", video_refs[0])

    return normalized


def _mode_for(spec: ModelSpec, parameters: dict[str, Any], input_url: str | None) -> str:
    if spec.operation == "motion_control":
        return "motion"
    if spec.media_type == "image":
        return "i2i" if has_references(parameters, input_url) else "t2i"
    if spec.media_type == "video":
        if spec.operation in {"video_edit", "video_upscale", "video_extend"}:
            return spec.operation
        return "i2v" if has_references(parameters, input_url) else "t2v"
    return spec.operation


def resolve_model_request(
    model_id: str,
    parameters: dict[str, Any] | None,
    *,
    input_url: str | None = None,
) -> RoutedModelRequest:
    requested_model_id = str(model_id)
    initial_parameters = dict(parameters or {})
    resolved_model_id = _select_model_id(requested_model_id, initial_parameters, input_url)
    spec = ModelCatalog.get(resolved_model_id)
    normalized_parameters = _apply_reference_aliases(spec, initial_parameters, input_url)
    mode = _mode_for(spec, normalized_parameters, input_url)
    return RoutedModelRequest(
        requested_model_id=requested_model_id,
        model_id=resolved_model_id,
        spec=spec,
        parameters=normalized_parameters,
        mode=mode,
        switched=resolved_model_id != requested_model_id,
    )
