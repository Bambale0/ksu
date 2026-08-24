from __future__ import annotations

from typing import Any

from app.services.kie_video_contracts import KieVideoContractError

SEEDANCE_REFERENCE_MODELS = {
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
    "bytedance/seedance-2-5",
}
SEEDANCE_REFERENCE_FIELDS = (
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
)


def enforce_seedance_reference_mode(model: str, payload: dict[str, Any]) -> None:
    """Enforce Seedance's documented frame-vs-reference mode split.

    Seedance 2.x has two separate reference flows:
    - temporal frame mode: first_frame_url and optional last_frame_url;
    - multimodal reference mode: reference_image_urls/reference_video_urls/reference_audio_urls.

    Mixing those modes creates ambiguous provider requests: some deployments reject
    the task, while others accept it but ignore part of the references. Keep the
    boundary strict so ROXY does not charge for a request Kie will not honor.
    """

    if model not in SEEDANCE_REFERENCE_MODELS:
        return

    first = bool(payload.get("first_frame_url"))
    last = bool(payload.get("last_frame_url"))
    reference_mode = any(bool(payload.get(field)) for field in SEEDANCE_REFERENCE_FIELDS)

    if last and not first:
        raise KieVideoContractError("Seedance last frame requires a first frame")
    if (first or last) and reference_mode:
        raise KieVideoContractError(
            "Seedance frame mode and multimodal reference mode are mutually exclusive"
        )
