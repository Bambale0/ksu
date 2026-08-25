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
    """Validate Seedance reference mode at the last provider boundary.

    Seedance 2.0 / Fast / Mini support hybrid control: temporal first/last
    frames can travel with multimodal reference arrays. Seedance 2.5 keeps the
    stricter frame-vs-reference split and must reject mixed payloads before Kie
    receives them.
    """

    if model not in SEEDANCE_REFERENCE_MODELS:
        return

    first = bool(payload.get("first_frame_url"))
    last = bool(payload.get("last_frame_url"))
    reference_mode = any(bool(payload.get(field)) for field in SEEDANCE_REFERENCE_FIELDS)

    if last and not first:
        raise KieVideoContractError("Seedance last frame requires a first frame")
    if model in SEEDANCE_STRICT_REFERENCE_MODELS and (first or last) and reference_mode:
        raise KieVideoContractError(
            "Seedance frame mode and multimodal reference mode are mutually exclusive"
        )
