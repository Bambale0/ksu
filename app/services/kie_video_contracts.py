from __future__ import annotations

from copy import deepcopy
from typing import Any


class KieVideoContractError(ValueError):
    pass


VIDEO_MODELS = {
    "wan/2-7-text-to-video",
    "wan/2-7-image-to-video",
    "wan/2-7-videoedit",
    "wan/2-7-r2v",
    "bytedance/seedance-1.5-pro",
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
    "bytedance/seedance-2-5",
    "kling-3.0/video",
    "kling-2.6/motion-control",
    "kling-3.0/motion-control",
    "gemini-omni-video",
    "grok-imagine/text-to-video",
    "grok-imagine/image-to-video",
    "grok-imagine-video-1-5-preview",
    "grok-imagine/upscale",
    "grok-imagine/extend",
}

SEEDANCE_20_MODELS = {
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
}
SEEDANCE_2_MODELS = {*SEEDANCE_20_MODELS, "bytedance/seedance-2-5"}
MOTION_MODELS = {"kling-2.6/motion-control", "kling-3.0/motion-control"}
GROK_GENERATORS = {
    "grok-imagine/text-to-video",
    "grok-imagine/image-to-video",
    "grok-imagine-video-1-5-preview",
}


def _enum(payload: dict[str, Any], field: str, allowed: set[str]) -> None:
    value = payload.get(field)
    if value in (None, ""):
        return
    value = str(value)
    if value not in allowed:
        raise KieVideoContractError(
            f"Unsupported {field}={value!r}; expected one of {sorted(allowed)!r}"
        )
    payload[field] = value


def _bool(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if value is None:
        return
    if not isinstance(value, bool):
        raise KieVideoContractError(f"{field} must be boolean")


def _int_range(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
    allow_zero: bool = False,
) -> None:
    value = payload.get(field)
    if value in (None, ""):
        return
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise KieVideoContractError(f"{field} must be an integer") from exc
    if allow_zero and normalized == 0:
        payload[field] = 0
        return
    if not minimum <= normalized <= maximum:
        raise KieVideoContractError(f"{field} must be between {minimum} and {maximum}")
    payload[field] = normalized


def _list(payload: dict[str, Any], field: str, *, maximum: int | None = None) -> list[Any]:
    value = payload.get(field)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise KieVideoContractError(f"{field} must be an array")
    if maximum is not None and len(value) > maximum:
        raise KieVideoContractError(f"{field} accepts at most {maximum} items")
    return value


def _looks_like_kling_video_url(value: Any) -> bool:
    path = str(value or "").split("?", 1)[0].lower()
    return path.endswith((".mp4", ".mov", ".qt", ".quicktime"))


def _normalize_wan(model: str, payload: dict[str, Any]) -> None:
    for field in ("prompt_extend", "watermark"):
        _bool(payload, field)

    if model == "wan/2-7-text-to-video":
        # Kie's 2.7 T2V contract calls this field `ratio`, while several other
        # Wan video endpoints call the same concept `aspect_ratio`.
        if payload.get("aspect_ratio") and not payload.get("ratio"):
            payload["ratio"] = payload["aspect_ratio"]
        payload.pop("aspect_ratio", None)
        return

    if model == "wan/2-7-image-to-video":
        first = bool(payload.get("first_frame_url"))
        last = bool(payload.get("last_frame_url"))
        clip = bool(payload.get("first_clip_url"))
        if clip and (first or last):
            raise KieVideoContractError(
                "Wan 2.7 continuation cannot be combined with first/last frames"
            )
        if last and not first:
            raise KieVideoContractError("Wan 2.7 last frame requires a first frame")
        if not first and not clip:
            raise KieVideoContractError(
                "Wan 2.7 image-to-video requires first_frame_url or first_clip_url"
            )
        return

    if model == "wan/2-7-videoedit":
        # Kie documents `audio_setting` as a scalar value (for example `auto`),
        # not the JSON object the legacy generic UI used to expose.
        audio_setting = payload.get("audio_setting")
        if isinstance(audio_setting, dict):
            if set(audio_setting) == {"mode"}:
                payload["audio_setting"] = str(audio_setting["mode"])
            else:
                raise KieVideoContractError("Wan video edit audio_setting must be a string")
        elif audio_setting not in (None, ""):
            payload["audio_setting"] = str(audio_setting)
        _int_range(payload, "duration", minimum=1, maximum=60, allow_zero=True)
        return

    if model == "wan/2-7-r2v":
        # R2V uses arrays for image/video references. Normalize legacy single
        # URL drafts so old users are not broken after the UI upgrade.
        for field in ("reference_image", "reference_video"):
            value = payload.get(field)
            if isinstance(value, str) and value:
                payload[field] = [value]
            elif value not in (None, "") and not isinstance(value, list):
                raise KieVideoContractError(f"{field} must be an array of URLs")


def _normalize_seedance(model: str, payload: dict[str, Any]) -> None:
    # Kie's published Seedance 2.0 example briefly contained a trailing-space
    # typo in this key. Accept old saved payloads, but only send the canonical
    # field to the provider.
    legacy_video_refs = payload.pop("reference_video_urls ", None)
    if legacy_video_refs not in (None, "") and not payload.get("reference_video_urls"):
        payload["reference_video_urls"] = legacy_video_refs

    if model == "bytedance/seedance-1.5-pro":
        for field in ("fixed_lens", "generate_audio", "nsfw_checker"):
            _bool(payload, field)
        _int_range(payload, "duration", minimum=1, maximum=30)
        _list(payload, "input_urls", maximum=2)
        return

    if model in SEEDANCE_20_MODELS:
        # Current Kie Seedance 2 / Fast / Mini request schemas do not expose the
        # legacy fixed_lens or return_last_frame fields. Old ROXY drafts used to
        # include them (return_last_frame=false even by default), which made Kie
        # reject otherwise valid requests before a task appeared in the dashboard.
        payload.pop("fixed_lens", None)
        payload.pop("return_last_frame", None)
        for field in ("generate_audio", "nsfw_checker", "web_search"):
            _bool(payload, field)

        _int_range(payload, "duration", minimum=4, maximum=15)
        if model in {"bytedance/seedance-2", "bytedance/seedance-2-fast"}:
            # The current Kie form does not list `adaptive` for Seedance 2 or
            # Seedance 2 Fast. Normalize legacy defaults to a documented ratio.
            if payload.get("aspect_ratio") == "adaptive":
                payload["aspect_ratio"] = "16:9"
            _enum(payload, "aspect_ratio", {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"})
        else:
            _enum(
                payload,
                "aspect_ratio",
                {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"},
            )
        seedance_20_resolutions = (
            {"480p", "720p", "1080p"}
            if model == "bytedance/seedance-2"
            else {"480p", "720p"}
        )
        _enum(payload, "resolution", seedance_20_resolutions)

        first = bool(payload.get("first_frame_url"))
        last = bool(payload.get("last_frame_url"))
        if last and not first:
            raise KieVideoContractError("Seedance last frame requires a first frame")

        # Seedance 2.0 supports hybrid control: first/last temporal frames may be
        # combined with multimodal reference arrays. The previous local mutual-
        # exclusion check stopped these requests before KieClient.post().
        _list(payload, "reference_image_urls", maximum=9)
        _list(payload, "reference_video_urls", maximum=3)
        _list(payload, "reference_audio_urls", maximum=3)
        return

    if model == "bytedance/seedance-2-5":
        for field in ("generate_audio", "nsfw_checker", "return_last_frame", "web_search"):
            _bool(payload, field)
        payload.pop("fixed_lens", None)
        _int_range(payload, "duration", minimum=4, maximum=30)
        if payload.get("resolution") == "4K":
            payload["resolution"] = "4k"
        _enum(payload, "resolution", {"480p", "720p", "1080p"})
        _enum(
            payload,
            "aspect_ratio",
            {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"},
        )
        _enum(payload, "output_format", {"mp4", "mov"})

        first = bool(payload.get("first_frame_url"))
        last = bool(payload.get("last_frame_url"))
        image_refs = _list(payload, "reference_image_urls", maximum=30)
        video_refs = _list(payload, "reference_video_urls", maximum=10)
        audio_refs = _list(payload, "reference_audio_urls", maximum=10)
        if last and not first:
            raise KieVideoContractError("Seedance last frame requires a first frame")
        if (first or last) and (image_refs or video_refs or audio_refs):
            # Keep 2.5's explicit frame-vs-reference mode separation. Unlike 2.0,
            # this rule is also enforced in the pre-billing Seedance 2.5 contract.
            raise KieVideoContractError(
                "Seedance 2.5 frame mode and multimodal reference mode are mutually exclusive"
            )


def _normalize_kling_3(payload: dict[str, Any]) -> None:
    _enum(payload, "mode", {"std", "pro", "4K"})
    _enum(payload, "aspect_ratio", {"16:9", "9:16", "1:1"})
    _int_range(payload, "duration", minimum=3, maximum=15)
    _bool(payload, "sound")
    _bool(payload, "multi_shots")

    images = _list(payload, "image_urls", maximum=2)
    multi_shots = bool(payload.get("multi_shots"))
    if multi_shots and len(images) > 1:
        raise KieVideoContractError("Kling multi-shot supports only the first frame image")

    shots = payload.get("multi_prompt") or []
    if multi_shots:
        if not isinstance(shots, list) or not 1 <= len(shots) <= 6:
            raise KieVideoContractError("Kling multi-shot requires 1-6 shots")
        total = 0
        for shot in shots:
            if not isinstance(shot, dict):
                raise KieVideoContractError("Every Kling shot must be an object")
            prompt = str(shot.get("prompt") or "").strip()
            if not prompt:
                raise KieVideoContractError("Every Kling shot requires a prompt")
            if len(prompt) > 500:
                raise KieVideoContractError("Kling shot prompt must be at most 500 chars")
            try:
                duration = int(shot.get("duration"))
            except (TypeError, ValueError) as exc:
                raise KieVideoContractError("Every Kling shot requires duration") from exc
            if not 1 <= duration <= 12:
                raise KieVideoContractError("Kling shot duration must be 1-12 seconds")
            shot["duration"] = duration
            total += duration
        if payload.get("duration") not in (None, "") and total != int(payload["duration"]):
            raise KieVideoContractError(
                "Kling multi-shot durations must add up to total duration"
            )
    elif shots:
        payload.pop("multi_prompt", None)

    elements = payload.get("kling_elements") or []
    if not isinstance(elements, list) or len(elements) > 3:
        raise KieVideoContractError("Kling accepts at most three elements")
    for element in elements:
        if not isinstance(element, dict):
            raise KieVideoContractError("Kling elements must be objects")
        name = str(element.get("name") or "").strip()
        if not name:
            raise KieVideoContractError("Every Kling element requires a name")
        refs = element.get("element_input_urls") or []
        audio_refs = element.get("element_input_audio_urls") or []
        if not isinstance(refs, list) or not isinstance(audio_refs, list):
            raise KieVideoContractError("Kling element references must be arrays")
        if len(audio_refs) > 1:
            raise KieVideoContractError("Kling element accepts at most one audio reference")
        if not refs and not audio_refs:
            raise KieVideoContractError("Kling element requires image/video/audio references")
        if len(refs) > 4:
            raise KieVideoContractError("Kling element accepts one video or 2-4 images")
        if len(refs) == 1:
            has_times = all(key in element for key in ("start_time", "end_time"))
            if not has_times and not _looks_like_kling_video_url(refs[0]):
                raise KieVideoContractError(
                    "Kling single URL element must be an MP4/MOV video reference"
                )
            if has_times:
                try:
                    start = int(element.get("start_time") or 0)
                    end = int(element.get("end_time") or 0)
                except (TypeError, ValueError) as exc:
                    raise KieVideoContractError(
                        "Kling video element start/end must be milliseconds"
                    ) from exc
                if start < 0 or end <= start or end - start < 3000 or end - start > 8000:
                    raise KieVideoContractError(
                        "Kling video element effective segment must be within 3-8 seconds"
                    )
                element["start_time"] = start
                element["end_time"] = end
        elif refs and not 2 <= len(refs) <= 4:
            raise KieVideoContractError("Kling image element requires 2-4 reference images")


def _normalize_motion(model: str, payload: dict[str, Any]) -> None:
    images = _list(payload, "input_urls", maximum=1)
    videos = _list(payload, "video_urls", maximum=1)
    if len(images) != 1 or len(videos) != 1:
        raise KieVideoContractError(
            "Kling Motion requires exactly one reference image and one motion video"
        )
    _enum(payload, "mode", {"720p", "1080p"})
    if payload.get("character_orientation") not in (None, ""):
        _enum(payload, "character_orientation", {"image", "video"})
    if model == "kling-3.0/motion-control" and payload.get("background_source") not in (None, ""):
        _enum(payload, "background_source", {"input_video", "input_image"})


def _normalize_gemini(payload: dict[str, Any]) -> None:
    images = _list(payload, "image_urls")
    videos = _list(payload, "video_list", maximum=1)
    characters = _list(payload, "character_ids", maximum=3)
    _list(payload, "audio_ids")
    if len(images) + len(videos) * 2 + len(characters) > 7:
        raise KieVideoContractError("Gemini Omni upload quota exceeds 7 units")
    for video in videos:
        if not isinstance(video, dict) or not str(video.get("url") or "").strip():
            raise KieVideoContractError("Gemini Omni video_list item requires url")
        start = video.get("start")
        ends = video.get("ends")
        if start is not None and ends is not None and float(ends) <= float(start):
            raise KieVideoContractError("Gemini Omni video end must be after start")


def _normalize_grok(model: str, payload: dict[str, Any]) -> None:
    if model in GROK_GENERATORS:
        if model != "grok-imagine-video-1-5-preview":
            if payload.get("mode") in (None, ""):
                payload["mode"] = "normal"
            _enum(payload, "mode", {"normal"})
        _int_range(payload, "duration", minimum=1, maximum=30)
        if model == "grok-imagine/image-to-video":
            _list(payload, "image_urls", maximum=1)
        return

    if model in {"grok-imagine/upscale", "grok-imagine/extend"}:
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise KieVideoContractError("Grok operation requires Kie task_id")
        payload["task_id"] = task_id
    if model == "grok-imagine/extend":
        # Current Kie docs use a numeric extension point and numeric repeat count.
        if payload.get("extend_at") not in (None, ""):
            _int_range(payload, "extend_at", minimum=0, maximum=600)
        if payload.get("extend_times") not in (None, ""):
            _int_range(payload, "extend_times", minimum=1, maximum=60)


def normalize_kie_video_input(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize current Kie Market video request contracts.

    Unknown/future models are intentionally passed through unchanged. This
    layer exists to prevent the Mini App from sending known invalid parameter
    combinations while keeping provider evolution backwards compatible.
    """

    payload = deepcopy(input_data)
    if model not in VIDEO_MODELS:
        return payload

    if model.startswith("wan/2-7-"):
        _normalize_wan(model, payload)
    elif model.startswith("bytedance/seedance-"):
        _normalize_seedance(model, payload)
    elif model == "kling-3.0/video":
        _normalize_kling_3(payload)
    elif model in MOTION_MODELS:
        _normalize_motion(model, payload)
    elif model == "gemini-omni-video":
        _normalize_gemini(payload)
    elif model.startswith("grok-imagine"):
        _normalize_grok(model, payload)

    return payload


def normalize_kie_veo_input(input_data: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(input_data)
    model = str(payload.get("veo_model") or "veo3_fast")
    if model not in {"veo3", "veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"}:
        raise KieVideoContractError("Unsupported Veo 3.1 model variant")
    payload["veo_model"] = model

    aspect = str(payload.get("aspect_ratio") or "16:9")
    if aspect not in {"auto", "16:9", "9:16"}:
        raise KieVideoContractError("Veo 3.1 aspect_ratio must be auto, 16:9 or 9:16")
    payload["aspect_ratio"] = aspect

    generation_type = str(payload.get("generation_type") or "TEXT_2_VIDEO")
    allowed_types = {
        "TEXT_2_VIDEO",
        "FIRST_AND_LAST_FRAMES_2_VIDEO",
        "REFERENCE_2_VIDEO",
    }
    if generation_type not in allowed_types:
        raise KieVideoContractError("Unsupported Veo 3.1 generation type")
    payload["generation_type"] = generation_type

    images = _list(payload, "image_urls", maximum=3)
    if generation_type == "TEXT_2_VIDEO" and images:
        # A single image is accepted by Kie's image-to-video flow under the
        # normal generation endpoint; preserve it instead of silently dropping it.
        pass
    elif generation_type == "FIRST_AND_LAST_FRAMES_2_VIDEO" and not 1 <= len(images) <= 2:
        raise KieVideoContractError("Veo first/last-frame mode requires one or two images")
    elif generation_type == "REFERENCE_2_VIDEO":
        if not images:
            raise KieVideoContractError("Veo reference mode requires material images")
        if model not in {"veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"}:
            raise KieVideoContractError("Veo reference mode is available only on Fast/Lite variants")

    for field in ("enable_fallback", "enable_translation"):
        _bool(payload, field)
    return payload
