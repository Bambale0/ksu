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


def _reference_urls(value: object) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        if item and _contains_private_url(item):
            return [item]
        raise ValueError("Private repeat reference must be an uploaded media URL")
    if isinstance(value, list) and value:
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or not _contains_private_url(item):
                raise ValueError("Private repeat references must be uploaded media URLs")
            result.append(item.strip())
        return result
    raise ValueError("Private repeat reference must be an uploaded media URL")


def repeat_reference_urls(reference_parameters: dict[str, Any]) -> list[str]:
    """Collect the media URLs supplied by a repeat recipient after shape validation."""

    values: list[str] = []
    for value in reference_parameters.values():
        values.extend(_reference_urls(value))
    return list(dict.fromkeys(values))


def sanitize_repeat_recipe(payload: dict[str, object]) -> dict[str, object]:
    """Strip owner media while retaining the hidden server-side generation recipe."""

    raw_parameters = payload.get("parameters")
    parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
    clean_parameters: dict[str, Any] = {}
    reference_fields: list[str] = []
    removed_private_media = bool(payload.get("references_required"))

    if payload.get("input_url"):
        removed_private_media = True
        reference_fields.append("input_url")

    for raw_key, value in parameters.items():
        key = str(raw_key)
        if key.casefold() in _PRIVATE_MEDIA_FIELDS:
            if value not in (None, "", [], {}):
                removed_private_media = True
                if key not in reference_fields:
                    reference_fields.append(key)
            continue
        if _contains_private_url(value):
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
    if reference_fields:
        # Field names are safe routing metadata; source URLs and values remain server-only.
        result["reference_fields"] = reference_fields
    return result


def public_repeat_descriptor(recipe: dict[str, object]) -> dict[str, object]:
    """Return only metadata that is safe for a repeat-link recipient to inspect."""

    result: dict[str, object] = {
        "model_id": str(recipe.get("model_id") or ""),
        "references_required": bool(recipe.get("references_required")),
    }
    reference_fields = recipe.get("reference_fields")
    if isinstance(reference_fields, list):
        result["reference_fields"] = [str(item) for item in reference_fields if str(item)]
    return result


def public_repeat_quote(quote: dict[str, Any]) -> dict[str, str]:
    """Expose only the recipient's payable price, never recipe-derived quote metadata."""

    cost = quote.get("effective_cost_rox")
    if cost is None:
        cost = quote.get("cost_rox")
    return {"cost_rox": str(cost or "0.00")}


def apply_repeat_reference_parameters(
    recipe: dict[str, object],
    reference_parameters: dict[str, Any],
) -> dict[str, object]:
    """Merge recipient-owned media without exposing or allowing recipe overrides."""

    parameters = dict(recipe.get("parameters") or {})
    input_url = recipe.get("input_url")
    raw_allowed = recipe.get("reference_fields")
    allowed_by_normalized = {
        str(item).casefold(): str(item)
        for item in raw_allowed
        if str(item)
    } if isinstance(raw_allowed, list) else {}
    allowed = set(allowed_by_normalized)
    references_required = bool(recipe.get("references_required"))

    if reference_parameters and not references_required:
        raise ValueError("This private repeat does not accept reference uploads")
    if references_required and not reference_parameters:
        raise ValueError("Add the required reference before repeating")

    supplied: set[str] = set()
    for raw_key, value in reference_parameters.items():
        key = str(raw_key)
        normalized = key.casefold()
        if normalized not in _PRIVATE_MEDIA_FIELDS:
            raise ValueError("Private repeat accepts only reference uploads")
        if allowed and normalized not in allowed:
            raise ValueError("Reference field does not belong to this private repeat")

        urls = _reference_urls(value)
        supplied.add(normalized)
        canonical_key = allowed_by_normalized.get(normalized, key)
        if normalized == "input_url":
            if len(urls) != 1:
                raise ValueError("Private repeat input reference must be a single uploaded media URL")
            input_url = urls[0]
        else:
            parameters[canonical_key] = urls[0] if isinstance(value, str) else urls

    missing = allowed - supplied
    if missing:
        raise ValueError("Add the required reference before repeating")
    if references_required and not supplied:
        raise ValueError("Add the required reference before repeating")

    return {
        "model_id": str(recipe.get("model_id") or ""),
        "prompt": str(recipe.get("prompt") or ""),
        "input_url": input_url,
        "billing_seconds": recipe.get("billing_seconds"),
        "parameters": parameters,
    }
