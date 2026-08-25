from __future__ import annotations

from typing import Any

from app.services.kie_video_contracts import KieVideoContractError

SEEDANCE_REFERENCE_MODELS = {
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
    "bytedance/seedance-2-5",
}
SEEDANCE_STRICT_REFERENCE_MODELS = {"bytedance/seedance-2-5"}
SEEDANCE_REFERENCE_FIELDS = (
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
)


def enforce_seedance_reference_mode(model: str, payload: dict[str, Any]) -> None:
    """Normalize Seedance's documented mutually-exclusive reference scenarios.

    Kie's Seedance 2.x docs define three separate scenarios:
    - first-frame image-to-video;
    - first+last-frame image-to-video;
    - multimodal reference-to-video.

    Legacy ROXY clients could submit first/last frame fields together with
    reference_* arrays. When reference arrays are present, keep the documented
    multimodal reference mode and remove temporal frame fields before provider
    submission instead of sending an ambiguous Kie request.
    """

    if model not in SEEDANCE_REFERENCE_MODELS:
        return

    reference_mode = any(bool(payload.get(field)) for field in SEEDANCE_REFERENCE_FIELDS)
    first = bool(payload.get("first_frame_url"))
    last = bool(payload.get("last_frame_url"))
    if model in SEEDANCE_STRICT_REFERENCE_MODELS and (first or last) and reference_mode:
        raise KieVideoContractError(
            "Seedance frame mode and multimodal reference mode are mutually exclusive"
        )
    if reference_mode:
        payload.pop("first_frame_url", None)
        payload.pop("last_frame_url", None)
        payload.pop("first_frame", None)
        return

    if last and not first:
        raise KieVideoContractError("Seedance last frame requires a first frame")
