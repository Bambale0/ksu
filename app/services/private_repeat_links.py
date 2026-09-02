from __future__ import annotations

import base64
import hashlib
import hmac
import re
import uuid
from typing import Any

from app.core.config import settings

_REPEAT_VERSION = "v1"
_TOKEN_RE = re.compile(r"^(?P<generation>[0-9a-f]{32})_(?P<signature>[A-Za-z0-9_-]{16})$")

# These values are owned media or provider/upload references. A private repeat
# link is intentionally a recipe capability, never a capability to the owner's
# files. Keep the deny-list broad because providers use several historical names.
_PRIVATE_MEDIA_FIELDS = frozenset(
    {
        "input_url",
        "input_urls",
        "image_input",
        "image_inputs",
        "input_image_url",
        "input_image_urls",
        "image_url",
        "image_urls",
        "reference_image",
        "reference_images",
        "reference_image_url",
        "reference_image_urls",
        "first_frame",
        "first_frame_url",
        "first_frame_image_url",
        "last_frame",
        "last_frame_url",
        "last_frame_image_url",
        "video_url",
        "video_urls",
        "reference_video",
        "reference_videos",
        "reference_video_url",
        "reference_video_urls",
        "first_clip_url",
        "audio_url",
        "audio_urls",
        "reference_audio",
        "reference_audios",
        "reference_audio_url",
        "reference_audio_urls",
    }
)


def _secret() -> bytes:
    # Production deploy guarantees ADMIN_SECURITY_KEY is persistent. The other
    # values keep local/test environments usable without introducing a new secret.
    raw = (
        settings.admin_security_key
        or settings.internal_admin_hmac_secret
        or settings.bot_token
    )
    if not raw:
        raise RuntimeError("Private repeat links are not configured")
    return raw.encode("utf-8")


def _signature(generation_id: uuid.UUID) -> str:
    message = f"roxy:{_REPEAT_VERSION}:repeat:{generation_id.hex}".encode("ascii")
    digest = hmac.new(_secret(), message, hashlib.sha256).digest()[:12]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def repeat_token(generation_id: uuid.UUID) -> str:
    """Return a compact capability token safe for Telegram's startapp payload."""

    return f"{generation_id.hex}_{_signature(generation_id)}"


def generation_id_from_repeat_token(token: str) -> uuid.UUID | None:
    match = _TOKEN_RE.fullmatch(str(token or "").strip())
    if match is None:
        return None
    generation_id = uuid.UUID(hex=match.group("generation"))
    expected = _signature(generation_id)
    if not hmac.compare_digest(expected, match.group("signature")):
        return None
    return generation_id


def _contains_private_url(value: object) -> bool:
    if isinstance(value, str):
        text = value.strip().lower()
        return (
            text.startswith("http://")
            or text.startswith("https://")
            or text.startswith("blob:")
            or text.startswith("data:")
            or "/uploads/" in text
            or "/api/v1/uploads/" in text
        )
    if isinstance(value, list):
        return any(_contains_private_url(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_private_url(item) for item in value.values())
    return False


def sanitize_repeat_recipe(payload: dict[str, object]) -> dict[str, object]:
    """Strip every owner-media capability from a reusable generation recipe."""

    raw_parameters = payload.get("parameters")
    parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
    clean_parameters: dict[str, Any] = {}
    removed_private_media = bool(payload.get("input_url")) or bool(payload.get("references_required"))

    for raw_key, value in parameters.items():
        key = str(raw_key)
        if key.casefold() in _PRIVATE_MEDIA_FIELDS or _contains_private_url(value):
            removed_private_media = True
            continue
        clean_parameters[key] = value

    result: dict[str, object] = {
        "model_id": str(payload.get("model_id") or ""),
        "prompt": str(payload.get("prompt") or ""),
        "input_url": None,
        "billing_seconds": payload.get("billing_seconds"),
        "parameters": clean_parameters,
    }
    if removed_private_media:
        result["references_required"] = True
    return result
