from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.model_catalog import InvalidModelParametersError

SEEDANCE25_MODEL_ID = "seedance-2.5"
SEEDANCE25_PROVIDER_MODEL = "bytedance/seedance-2-5"

# Follow Kie's callable input schema, not broader marketing capability claims.
SEEDANCE25_RESOLUTIONS = {"480p", "720p"}
SEEDANCE25_ASPECT_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}
SEEDANCE25_OUTPUT_FORMATS = {"mp4", "mov"}
SEEDANCE25_MIN_DURATION = 4
SEEDANCE25_MAX_DURATION = 30
SEEDANCE25_MAX_IMAGE_REFS = 30
SEEDANCE25_MAX_VIDEO_REFS = 10
SEEDANCE25_MAX_AUDIO_REFS = 10
SEEDANCE25_FIELDS = {
    "prompt",
    "first_frame_url",
    "last_frame_url",
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
    "generate_audio",
    "return_last_frame",
    "resolution",
    "aspect_ratio",
    "duration",
    "output_format",
    "web_search",
    "nsfw_checker",
}


def _bool(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if value is not None and not isinstance(value, bool):
        raise InvalidModelParametersError(f"Seedance 2.5 {field} must be boolean")


def _enum(payload: dict[str, Any], field: str, allowed: set[str]) -> None:
    value = payload.get(field)
    if value in (None, ""):
        return
    normalized = str(value)
    if normalized not in allowed:
        raise InvalidModelParametersError(
            f"Unsupported Seedance 2.5 {field}={normalized!r}; expected one of {sorted(allowed)!r}"
        )
    payload[field] = normalized


def _refs(payload: dict[str, Any], field: str, maximum: int) -> list[Any]:
    value = payload.get(field)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise InvalidModelParametersError(f"Seedance 2.5 {field} must be an array")
    if len(value) > maximum:
        raise InvalidModelParametersError(
            f"Seedance 2.5 {field} accepts at most {maximum} items"
        )
    return value


def normalize_seedance25_input(parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate Seedance 2.5 before wallet debit/provider submission.

    Provider auto-duration remains intentionally disabled: ROXY charges video
    per second before submission, so an unknown final duration cannot be safely
    debited with the current accounting contract. Fixed 4-30 second jobs keep
    quote and debit deterministic.
    """

    payload = deepcopy(parameters)

    # `fixed_lens` belongs to older Seedance contracts. Drop it from saved
    # drafts instead of forwarding an obsolete field to Seedance 2.5.
    payload.pop("fixed_lens", None)

    unsupported = sorted(
        key for key in payload if not key.startswith("_") and key not in SEEDANCE25_FIELDS
    )
    if unsupported:
        raise InvalidModelParametersError(
            f"Unsupported Seedance 2.5 field: {unsupported[0]}"
        )

    # Internal metadata is never part of a provider request. ModelCatalog also
    # strips it later, but removing it here keeps this provider boundary strict.
    payload = {key: value for key, value in payload.items() if not key.startswith("_")}

    for field in ("generate_audio", "return_last_frame", "web_search", "nsfw_checker"):
        _bool(payload, field)

    _enum(payload, "resolution", SEEDANCE25_RESOLUTIONS)
    _enum(payload, "aspect_ratio", SEEDANCE25_ASPECT_RATIOS)
    _enum(payload, "output_format", SEEDANCE25_OUTPUT_FORMATS)

    duration = payload.get("duration")
    if duration not in (None, ""):
        try:
            normalized_duration = int(duration)
        except (TypeError, ValueError) as exc:
            raise InvalidModelParametersError("Seedance 2.5 duration must be an integer") from exc
        if not SEEDANCE25_MIN_DURATION <= normalized_duration <= SEEDANCE25_MAX_DURATION:
            raise InvalidModelParametersError(
                f"Seedance 2.5 duration must be {SEEDANCE25_MIN_DURATION}-{SEEDANCE25_MAX_DURATION} seconds"
            )
        payload["duration"] = normalized_duration

    image_refs = _refs(payload, "reference_image_urls", SEEDANCE25_MAX_IMAGE_REFS)
    video_refs = _refs(payload, "reference_video_urls", SEEDANCE25_MAX_VIDEO_REFS)
    audio_refs = _refs(payload, "reference_audio_urls", SEEDANCE25_MAX_AUDIO_REFS)

    first = bool(payload.get("first_frame_url"))
    last = bool(payload.get("last_frame_url"))
    reference_mode = bool(image_refs or video_refs or audio_refs)
    if last and not first:
        raise InvalidModelParametersError("Seedance 2.5 last frame requires a first frame")
    if (first or last) and reference_mode:
        raise InvalidModelParametersError(
            "Seedance 2.5 frame mode and multimodal reference mode are mutually exclusive"
        )

    return payload
