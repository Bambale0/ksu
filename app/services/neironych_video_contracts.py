from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

from app.services.seedance_reference_integrity import seedance_reference_requirements


class NeironychVideoContractError(ValueError):
    pass


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
    if parsed.scheme != "https" or not parsed.netloc:
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

    family = _family(model)
    payload = deepcopy(input_data)

    # Model identity is owned by the trusted admin selection / runtime resolver.
    payload.pop("model", None)

    for field in _ALWAYS_DROP_FIELDS:
        payload.pop(field, None)
    if payload.get("generate_audio") is False:
        raise NeironychVideoContractError(
            "generate_audio=false не поддерживается Нейронычем для Seedance."
        )
    elif "generate_audio" in payload and not isinstance(payload["generate_audio"], bool):
        raise NeironychVideoContractError("generate_audio должен быть boolean.")

    prompt = _validate_prompt(payload)

    duration = payload.get("duration")
    if duration not in (None, ""):
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
    if has_frames and has_refs:
        raise NeironychVideoContractError(
            "Frame mode нельзя смешивать с reference media."
        )

    aspect_ratio = str(payload.get("aspect_ratio") or "").strip()
    if aspect_ratio:
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
        elif task_type not in {"auto", "reference", "edit"}:
            raise NeironychVideoContractError(
                "omni_reference_task_type: auto, reference или edit."
            )
        elif task_type == "edit" and not video_refs:
            raise NeironychVideoContractError(
                "Seedance 2.5 edit требует видео-референс."
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
