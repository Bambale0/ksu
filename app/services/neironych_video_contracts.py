from __future__ import annotations

from copy import deepcopy
import re
from typing import Any
from urllib.parse import urlsplit

from app.services.seedance_reference_integrity import seedance_reference_requirements


class NeironychVideoContractError(ValueError):
    pass


class NeironychVideoUnsupportedInput(NeironychVideoContractError):
    """Valid product input that this provider cannot represent without loss."""


def _normalize_grok(input_data: dict[str, Any]) -> dict[str, Any]:
    prompt = str(input_data.get("prompt") or "").strip()
    if not prompt:
        raise NeironychVideoContractError("Prompt must not be empty")
    duration = input_data.get("duration", 5)
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise NeironychVideoContractError("Grok duration must be an integer")
    if not 1 <= duration <= 15:
        raise NeironychVideoUnsupportedInput("Grok duration must be 1-15 seconds")
    resolution = str(input_data.get("resolution") or "480p")
    ratio = str(input_data.get("aspect_ratio") or "16:9")
    if resolution not in {"480p", "720p", "1080p"}:
        raise NeironychVideoUnsupportedInput("Unsupported Grok resolution")
    if ratio not in {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}:
        raise NeironychVideoUnsupportedInput("Unsupported Grok aspect ratio")
    known = {"model", "prompt", "duration", "resolution", "aspect_ratio", "image_urls", "reference_images", "image", "nsfw_checker"}
    if input_data.get("nsfw_checker") not in (None, False):
        raise NeironychVideoUnsupportedInput("Grok content filter cannot be configured through Neironych")
    if any(value not in (None, "", []) for key, value in input_data.items() if key not in known):
        raise NeironychVideoUnsupportedInput("Unsupported Grok control")
    source = deepcopy(input_data)
    raw_refs = source.get("reference_images") or source.get("image_urls") or []
    if isinstance(raw_refs, list) and len(raw_refs) > 7:
        raise NeironychVideoUnsupportedInput("Grok supports at most seven image references")
    refs = _reference_list(source, canonical="reference_images", legacy="image_urls", maximum=7)
    first_frame = source.get("image")
    if first_frame not in (None, ""):
        first_frame = _url_item(first_frame, field="image")
        if refs:
            raise NeironychVideoContractError("Grok first frame cannot be combined with references")
    if len(refs) > 7 or (refs and resolution == "1080p"):
        raise NeironychVideoUnsupportedInput("Grok references require at most seven images at 480p/720p")
    result: dict[str, Any] = {
        "prompt": prompt, "duration": duration, "resolution": resolution, "aspect_ratio": ratio,
    }
    if refs:
        result["reference_images"] = refs
    if first_frame:
        result["image"] = first_frame
    return result


_SEEDANCE_MODEL_FAMILY = {
    "seedance-2.0": "seedance-2.0",
    "seedance-2": "seedance-2.0",
    "bytedance/seedance-2.0": "seedance-2.0",
    "bytedance/seedance-2": "seedance-2.0",
    "seedance-2.5": "seedance-2.5",
    "bytedance/seedance-2.5": "seedance-2.5",
}

_FIXED_ASPECT_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "21:9"}
_RESOLUTIONS = {
    "seedance-2.0": {"480p", "720p", "1080p", "4k"},
    "seedance-2.5": {"480p", "720p", "1080p"},
}
_DURATION_RANGES = {
    "seedance-2.0": (4, 15),
    "seedance-2.5": (4, 30),
}
_REFERENCE_LIMITS = {
    "seedance-2.0": {"image": 9, "video": 3, "audio": 3, "total": 12},
    "seedance-2.5": {"image": 30, "video": 10, "audio": 10, "total": 50},
}
_ALWAYS_DROP_FIELDS = {
    "return_last_frame",
    "output_format",
    "web_search",
    "nsfw_checker",
    "fixed_lens",
}
_MAX_PROMPT_BYTES = 40_000
_DRAFT_TASK_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _family(model: str) -> str:
    value = str(model or "").strip()
    try:
        return _SEEDANCE_MODEL_FAMILY[value]
    except KeyError as exc:
        raise NeironychVideoContractError(f"Неподдерживаемая модель Seedance: {value}") from exc


def _url_item(value: Any, *, field: str) -> dict[str, str]:
    if isinstance(value, dict):
        raw = value.get("url")
    else:
        raw = value
    url = str(raw or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise NeironychVideoContractError(f"{field}: нужен HTTPS URL.")
    return {"url": url}


def _reference_list(
    payload: dict[str, Any],
    *,
    canonical: str,
    legacy: str,
    maximum: int,
) -> list[dict[str, str]]:
    raw = payload.get(canonical)
    if raw in (None, ""):
        raw = payload.pop(legacy, None)
    else:
        payload.pop(legacy, None)
    if raw in (None, ""):
        payload.pop(canonical, None)
        return []
    if not isinstance(raw, list):
        raise NeironychVideoContractError(f"{canonical}: ожидается массив.")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        normalized = _url_item(item, field=canonical)
        url = normalized["url"]
        if url not in seen:
            result.append(normalized)
            seen.add(url)
    if len(result) > maximum:
        raise NeironychVideoContractError(
            f"{canonical}: максимум {maximum} референсов."
        )
    if result:
        payload[canonical] = result
    else:
        payload.pop(canonical, None)
    return result


def _frame(
    payload: dict[str, Any],
    *,
    canonical: str,
    legacy: str,
) -> dict[str, str] | None:
    raw = payload.get(canonical)
    if raw in (None, ""):
        raw = payload.pop(legacy, None)
    else:
        payload.pop(legacy, None)
    if raw in (None, ""):
        payload.pop(canonical, None)
        return None
    normalized = _url_item(raw, field=canonical)
    payload[canonical] = normalized
    return normalized


def _validate_prompt(payload: dict[str, Any]) -> str:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise NeironychVideoContractError("Промпт не может быть пустым.")
    if len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
        raise NeironychVideoContractError(
            "Промпт Seedance превышает лимит 40 000 байт UTF-8."
        )
    payload["prompt"] = prompt
    return prompt


def normalize_neironych_video_input(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize the documented Neironych Seedance request before provider spend.

    Unknown future fields pass through so the admin lab can exercise provider
    additions, but known-invalid legacy ROXY/KIE fields are removed and all
    documented Seedance invariants are enforced locally.
    """

    if model == "grok-imagine-video-1.5":
        return _normalize_grok(input_data)
    family = _family(model)
    payload = deepcopy(input_data)

    # Model identity is owned by the trusted admin selection / runtime resolver.
    payload.pop("model", None)

    for field in _ALWAYS_DROP_FIELDS:
        payload.pop(field, None)

    draft_task = payload.get("draft_task")
    if draft_task is not None:
        if family != "seedance-2.5" or not isinstance(draft_task, dict):
            raise NeironychVideoContractError("draft_task доступен только для Seedance 2.5.")
        if set(draft_task) != {"id"}:
            raise NeironychVideoContractError("draft_task должен содержать только id.")
        task_id = draft_task.get("id")
        if not isinstance(task_id, str) or not _DRAFT_TASK_ID.fullmatch(task_id):
            raise NeironychVideoContractError("draft_task.id имеет недопустимый формат.")
        # ArgoLink requires the full render to contain only model + draft_task.
        # The trusted model is injected by the caller after this normalizer.
        return {"draft_task": {"id": task_id}}

    draft = payload.get("draft")
    if draft is not None and draft is not True:
        raise NeironychVideoContractError("draft должен быть true или отсутствовать.")
    if draft is True:
        if family != "seedance-2.5":
            raise NeironychVideoContractError("draft доступен только для Seedance 2.5.")
        payload["resolution"] = "480p"

    if "generate_audio" in payload and not isinstance(payload["generate_audio"], bool):
        raise NeironychVideoContractError("generate_audio должен быть boolean.")

    task_type = str(payload.get("omni_reference_task_type") or "").strip()
    is_edit = family == "seedance-2.5" and task_type == "edit"
    is_extend = family == "seedance-2.5" and task_type == "extend"
    if draft is True and (is_edit or is_extend):
        raise NeironychVideoContractError("draft нельзя совмещать с edit или extend.")
    if "seed" in payload:
        raise NeironychVideoContractError("seed is not supported by Seedance")
    if "watermark" in payload and payload["watermark"] is not False:
        raise NeironychVideoContractError("watermark=true is not supported by Seedance")
    if "n" in payload and (type(payload["n"]) is not int or payload["n"] != 1):
        raise NeironychVideoContractError("Seedance requires n=1")
    if is_edit and payload.get("size") not in (None, ""):
        raise NeironychVideoContractError("Seedance 2.5 edit follows source size")

    prompt = _validate_prompt(payload)

    if is_edit:
        # An edit keeps the source video's duration; legacy callers used -1.
        payload.pop("duration", None)
    duration = payload.get("duration")
    if duration not in (None, ""):
        if isinstance(duration, (bool, float)):
            raise NeironychVideoContractError("duration must be integer seconds")
        try:
            normalized_duration = int(duration)
        except (TypeError, ValueError) as exc:
            raise NeironychVideoContractError("duration должен быть целым числом.") from exc
        minimum, maximum = _DURATION_RANGES[family]
        if not minimum <= normalized_duration <= maximum:
            raise NeironychVideoContractError(
                f"duration для {family}: от {minimum} до {maximum} секунд."
            )
        payload["duration"] = normalized_duration

    resolution = str(payload.get("resolution") or "").strip()
    if resolution == "4K":
        resolution = "4k"
    if resolution:
        if resolution not in _RESOLUTIONS[family]:
            raise NeironychVideoContractError(
                f"resolution для {family}: {', '.join(sorted(_RESOLUTIONS[family]))}."
            )
        payload["resolution"] = resolution

    limits = _REFERENCE_LIMITS[family]
    image_refs = _reference_list(
        payload,
        canonical="reference_images",
        legacy="reference_image_urls",
        maximum=limits["image"],
    )
    video_refs = _reference_list(
        payload,
        canonical="reference_videos",
        legacy="reference_video_urls",
        maximum=limits["video"],
    )
    audio_refs = _reference_list(
        payload,
        canonical="reference_audios",
        legacy="reference_audio_urls",
        maximum=limits["audio"],
    )
    total_refs = len(image_refs) + len(video_refs) + len(audio_refs)
    if total_refs > limits["total"]:
        raise NeironychVideoContractError(
            f"Для {family} максимум {limits['total']} референсов суммарно."
        )
    if family == "seedance-2.0" and audio_refs and not (image_refs or video_refs):
        raise NeironychVideoContractError(
            "Для Seedance 2.0 аудио-референс требует хотя бы одно фото или видео."
        )

    start_image = _frame(
        payload,
        canonical="start_image",
        legacy="first_frame_url",
    )
    end_image = _frame(
        payload,
        canonical="end_image",
        legacy="last_frame_url",
    )
    if end_image and not start_image:
        raise NeironychVideoContractError("end_image требует start_image.")

    has_frames = bool(start_image or end_image)
    has_refs = bool(image_refs or video_refs or audio_refs)
    if (is_edit or is_extend) and has_frames:
        raise NeironychVideoContractError(
            "Seedance 2.5 edit/extend cannot use start_image/end_image"
        )
    if has_frames and has_refs:
        raise NeironychVideoContractError(
            "Frame mode нельзя смешивать с reference media."
        )

    if is_edit or is_extend:
        # Both operations inherit the source video's ratio.
        payload.pop("aspect_ratio", None)
    aspect_ratio = str(payload.get("aspect_ratio") or "").strip()
    if aspect_ratio:
        if family == "seedance-2.5" and has_frames and aspect_ratio != "adaptive":
            raise NeironychVideoContractError("Seedance 2.5 frame/edit requires adaptive or omitted aspect_ratio")
        if aspect_ratio == "adaptive":
            if not has_frames:
                raise NeironychVideoContractError(
                    "aspect_ratio=adaptive разрешён только со start_image/end_image."
                )
        elif aspect_ratio not in _FIXED_ASPECT_RATIOS:
            raise NeironychVideoContractError(
                "Неподдерживаемый aspect_ratio: "
                + ", ".join(sorted(_FIXED_ASPECT_RATIOS | {"adaptive"}))
                + "."
            )
        payload["aspect_ratio"] = aspect_ratio

    task_type = str(payload.get("omni_reference_task_type") or "").strip()
    if task_type:
        if family != "seedance-2.5":
            payload.pop("omni_reference_task_type", None)
        elif task_type not in {"auto", "reference", "edit", "extend"}:
            raise NeironychVideoContractError(
                "omni_reference_task_type: auto, reference, edit или extend."
            )
        elif task_type in {"edit", "extend"} and not video_refs:
            raise NeironychVideoContractError(
                f"Seedance 2.5 {task_type} требует видео-референс."
            )

    required = seedance_reference_requirements(prompt)
    available = {
        "image": len(image_refs),
        "video": len(video_refs),
        "audio": len(audio_refs),
    }
    missing: list[str] = []
    for kind, required_count in required.items():
        if required_count > available[kind]:
            missing.append(f"@{kind.title()}{required_count}")
    if missing:
        raise NeironychVideoContractError(
            "Промпт ссылается на отсутствующие референсы: " + ", ".join(missing)
        )

    return payload
