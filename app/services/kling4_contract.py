"""Kie Kling 4.0 request contract; shared by billing and the jobs adapter."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

MODEL_PROVIDERS = {
    "kling-4.0": "kling-4.0/reference-to-video",
    "kling-4.0-keyframe": "kling-4.0/keyframe-to-video",
}
COMMON_FIELDS = ("prompt", "duration", "resolution", "aspect_ratio")
REFERENCE_FIELDS = (*COMMON_FIELDS, "image_urls", "video_urls", "keep_original_sound", "elements", "voices")
KEYFRAME_FIELDS = (*COMMON_FIELDS, "first_frame_url", "keyframe_urls", "last_frame_url")
ASPECT_RATIOS = ("auto", "16:9", "9:16", "1:1", "21:9")
ELEMENT_TAGS = ("character", "animal", "prop", "costume", "scene", "effect", "others")
_NAME = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9_]{1,20}\Z")
_RESERVED = re.compile(r"(?:(?:image|video|keyframe|object|audio)_\d+|first_frame|last_frame)\Z", re.I)


class Kling4ContractError(ValueError):
    pass


def _url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise Kling4ContractError(f"{field} must be an HTTP(S) URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise Kling4ContractError(f"{field} must be an HTTP(S) URL") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise Kling4ContractError(f"{field} must be an HTTP(S) URL")
    return value


def _array(data: dict[str, Any], field: str, maximum: int) -> list[Any]:
    value = data.get(field, [])
    if not isinstance(value, list) or len(value) > maximum:
        raise Kling4ContractError(f"{field} must be an array with at most {maximum} items")
    return value


def _urls(data: dict[str, Any], field: str, maximum: int) -> list[str]:
    return [_url(item, field) for item in _array(data, field, maximum)]


def _fields(data: dict[str, Any], allowed: tuple[str, ...], label: str) -> None:
    extra = sorted(set(data) - set(allowed))
    if extra:
        raise Kling4ContractError(f"Unsupported {label} fields: {', '.join(extra)}")


def _name(data: dict[str, Any], names: set[str]) -> str:
    name = data.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name) or _RESERVED.fullmatch(name):
        raise Kling4ContractError("Reference name must contain 1–20 Chinese/Latin letters, digits or underscores and must not be reserved")
    if name.casefold() in names:
        raise Kling4ContractError("Element and voice names must be unique (case-insensitive)")
    names.add(name.casefold())
    return name


def _mentions(prompt: str, declared: set[str]) -> None:
    # Provider matches names exactly and prefers the longest declared name.
    names = sorted(declared, key=len, reverse=True)
    for marker in re.finditer("@", prompt):
        suffix = prompt[marker.end():]
        if not any(suffix.startswith(name) and (
            len(suffix) == len(name) or not re.match(r"[A-Za-z0-9_\u4e00-\u9fa5]", suffix[len(name)])
        ) for name in names):
            token = suffix.split()[0] if suffix.split() else ""
            raise Kling4ContractError(f"Undeclared reference @{token[:30]}")


def normalize_kling4_input(model: str, source: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(source)
    keyframes = model == MODEL_PROVIDERS["kling-4.0-keyframe"]
    if model not in MODEL_PROVIDERS.values():
        return data
    _fields(data, KEYFRAME_FIELDS if keyframes else REFERENCE_FIELDS, "Kling 4")
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
        raise Kling4ContractError("Kling 4 prompt must contain 1–8000 characters")
    duration = data.get("duration", 5)
    if isinstance(duration, str) and duration.isascii() and duration.isdigit():
        duration = int(duration)
    if type(duration) is not int or not 3 <= duration <= 30:
        raise Kling4ContractError("Kling 4 duration must be an integer from 3 to 30")
    data["duration"] = duration
    data.setdefault("resolution", "720p")
    if not isinstance(data["resolution"], str) or data["resolution"] not in {"720p", "1080p"}:
        raise Kling4ContractError("Kling 4 resolution must be 720p or 1080p")
    if "aspect_ratio" in data and data["aspect_ratio"] not in ASPECT_RATIOS:
        raise Kling4ContractError("Unsupported Kling 4 aspect_ratio")
    declared: set[str] = set()
    if keyframes:
        middle = _urls(data, "keyframe_urls", 8)
        first = data.get("first_frame_url")
        last = data.get("last_frame_url")
        if (middle or last) and not first:
            raise Kling4ContractError("Kling 4 keyframes require first_frame_url")
        for field in ("first_frame_url", "last_frame_url"):
            if field in data:
                _url(data[field], field)
                declared.add(field.removesuffix("_url"))
        count = bool(first) + len(middle) + bool(last)
        if count > min(duration + 1, 10):
            raise Kling4ContractError("Too many Kling 4 frames for the selected duration")
        declared.update(f"keyframe_{i + 1}" for i in range(len(middle)))
    else:
        images = _urls(data, "image_urls", 10)
        videos = _urls(data, "video_urls", 5)
        elements = _array(data, "elements", 7)
        voices = _array(data, "voices", 3)
        if sum(map(len, (images, videos, elements, voices))) > 15:
            raise Kling4ContractError("Kling 4 accepts at most 15 references in total")
        if "keep_original_sound" in data and type(data["keep_original_sound"]) is not bool:
            raise Kling4ContractError("keep_original_sound must be boolean")
        declared.update(f"image_{i + 1}" for i in range(len(images)))
        declared.update(f"video_{i + 1}" for i in range(len(videos)))
        names: set[str] = set()
        video_elements = 0
        for element in elements:
            if not isinstance(element, dict):
                raise Kling4ContractError("Kling 4 elements must be objects")
            _fields(element, ("name", "image_urls", "video_url", "tag", "description", "voice_url"), "element")
            declared.add(_name(element, names))
            element_images = _urls(element, "image_urls", 4)
            video = element.get("video_url")
            if ("image_urls" in element) == ("video_url" in element):
                raise Kling4ContractError("Each element requires either 2–4 images or one video")
            if "image_urls" in element and len(element_images) < 2:
                raise Kling4ContractError("Image elements require 2–4 images")
            if "video_url" in element:
                _url(video, "video_url")
                video_elements += 1
            tag = element.get("tag")
            if tag is not None and tag not in ELEMENT_TAGS:
                raise Kling4ContractError("Unsupported element tag")
            if video and tag not in (None, "character"):
                raise Kling4ContractError("Video elements must be characters")
            description = element.get("description", "")
            if not isinstance(description, str) or len(description) > 100:
                raise Kling4ContractError("Element description must be at most 100 characters")
            if "voice_url" in element:
                _url(element["voice_url"], "voice_url")
                if tag not in (None, "character"):
                    raise Kling4ContractError("Only character elements can bind a voice")
        if video_elements > 3 or video_elements + len(videos) > 5:
            raise Kling4ContractError("At most 3 video elements and 5 combined videos are allowed")
        for voice in voices:
            if not isinstance(voice, dict):
                raise Kling4ContractError("Kling 4 voices must be objects")
            _fields(voice, ("name", "audio_url"), "voice")
            declared.add(_name(voice, names))
            _url(voice.get("audio_url"), "audio_url")
    _mentions(prompt, declared)
    return data


async def validate_kling4_media(session: Any, data: dict[str, Any], *, user_id: Any = None) -> None:
    """Check measured video limits against owner-scoped upload metadata."""
    from sqlalchemy import select

    from app.db.reference_models import UserReference
    from app.services.model_catalog import InvalidModelParametersError

    videos = [(url, 2, 30) for url in data.get("video_urls", [])]
    videos.extend((item["video_url"], 3, 8) for item in data.get("elements", []) if item.get("video_url"))
    if not videos:
        return
    info = getattr(session, "info", {})
    owner = user_id or (info.get("current_user_id") if isinstance(info, dict) else None)
    if owner is None:
        raise InvalidModelParametersError("Kling 4 video duration requires an authenticated upload owner")
    total_ms = 0
    for url, minimum, maximum in videos:
        row = await session.scalar(select(UserReference).where(
            UserReference.user_id == owner, UserReference.source_url == url,
            UserReference.status == "ready", UserReference.kind == "video",
        ).order_by(UserReference.created_at.desc()).limit(1))
        if row is None or row.probe_status != "ready" or row.duration_ms is None:
            raise InvalidModelParametersError("Kling 4 video duration must be verified: upload through ROXY")
        if not minimum * 1000 <= row.duration_ms <= maximum * 1000:
            raise InvalidModelParametersError(f"Kling 4 reference video must be {minimum}–{maximum} seconds")
        total_ms += row.duration_ms
    if total_ms > 30000:
        raise InvalidModelParametersError("Kling 4 reference videos may total at most 30 seconds")


def kling4_reference_slots(data: dict[str, Any]) -> list[tuple[str, tuple[Any, ...]]]:
    """Ordered media roles, including every view and bound voice of a subject."""
    slots: list[tuple[str, tuple[Any, ...]]] = []
    if data.get("first_frame_url"):
        slots.append(("image", ("first_frame_url",)))
    slots.extend(("image", ("keyframe_urls", i)) for i in range(len(data.get("keyframe_urls", []))))
    if data.get("last_frame_url"):
        slots.append(("image", ("last_frame_url",)))
    for field, kind in (("image_urls", "image"), ("video_urls", "video")):
        slots.extend((kind, (field, i)) for i in range(len(data.get(field, []))))
    for i, element in enumerate(data.get("elements", [])):
        slots.extend(("image", ("elements", i, "image_urls", j)) for j in range(len(element.get("image_urls", []))))
        for field, kind in (("video_url", "video"), ("voice_url", "audio")):
            if element.get(field):
                slots.append((kind, ("elements", i, field)))
    slots.extend(("audio", ("voices", i, "audio_url")) for i in range(len(data.get("voices", []))))
    return slots


def replace_kling4_references(source: dict[str, Any], base: dict[str, Any], references: dict[str, list[str]]) -> dict[str, Any]:
    """Preserve server-owned roles while replacing every author media URL."""
    slots = kling4_reference_slots(source)
    expected = {kind: sum(slot_kind == kind for slot_kind, _ in slots) for kind in ("image", "video", "audio")}
    if any(len(references.get(kind, [])) < count for kind, count in expected.items()):
        raise Kling4ContractError("Add the requested Kling 4 image, video and audio references")
    result = deepcopy(base)
    for field in ("image_urls", "video_urls", "first_frame_url", "keyframe_urls", "last_frame_url", "elements", "voices"):
        if field in source:
            result[field] = deepcopy(source[field])
    positions = {kind: 0 for kind in expected}
    for kind, path in slots:
        target = result
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = references[kind][positions[kind]]
        positions[kind] += 1
    extra = {kind: references.get(kind, [])[count:] for kind, count in expected.items()}
    keyframes = source.get("_model_id") == "kling-4.0-keyframe" or any(field in source for field in ("first_frame_url", "keyframe_urls", "last_frame_url"))
    if keyframes:
        if extra["video"] or extra["audio"]:
            raise Kling4ContractError("Kling 4 keyframes accept image references only")
        images = list(extra["image"])
        if images and not result.get("first_frame_url"):
            result["first_frame_url"] = images.pop(0)
        if images:
            middle = [*result.get("keyframe_urls", []), *images]
            if len(middle) > 8 and not result.get("last_frame_url"):
                result["last_frame_url"] = middle.pop()
            result["keyframe_urls"] = middle
    else:
        for kind, field in (("image", "image_urls"), ("video", "video_urls")):
            if extra[kind]:
                result[field] = [*result.get(field, []), *extra[kind]]
        names = {str(item.get("name", "")).casefold() for field in ("elements", "voices") for item in result.get(field, [])}
        for url in extra["audio"]:
            index = 1
            while f"VoiceExtra{index}".casefold() in names:
                index += 1
            name = f"VoiceExtra{index}"
            result.setdefault("voices", []).append({"name": name, "audio_url": url})
            names.add(name.casefold())
    return result
