from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from app.core.config import settings

FeedLinkAction = Literal["ref", "feed", "posts", "remix"]

_REF_RE = re.compile(r"^ref_(\d+)$", re.IGNORECASE)
_POST_RE = re.compile(r"^feed_([0-9a-fA-F-]{36})(?:_ref_(\d+))?$", re.IGNORECASE)
_LEGACY_PROFILE_RE = re.compile(r"^posts_(\d+)_ref_(\d+)$", re.IGNORECASE)
_PROFILE_RE = re.compile(r"^profile_(\d+)(?:_ref_(\d+))?$", re.IGNORECASE)
_REMIX_RE = re.compile(r"^remix_([0-9a-fA-F-]{36})(?:_ref_(\d+))?$", re.IGNORECASE)
_MAIN_MINI_APP_SHORT_NAME_MARKERS = {"", "app", "main", "default"}


@dataclass(frozen=True, slots=True)
class FeedDeepLink:
    action: FeedLinkAction
    referral_telegram_id: int
    generation_id: uuid.UUID | None = None
    profile_referral_code: str | None = None


def _code(value: int | str) -> str:
    return str(value).strip().upper()


def referral_payload(telegram_id: int | str) -> str:
    return f"ref_{_code(telegram_id)}"


def post_payload(generation_id: uuid.UUID, referral_telegram_id: int | str | None = None) -> str:
    payload = f"feed_{generation_id}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def profile_payload(telegram_id: int | str) -> str:
    # Match banano_kling:tanyapi exactly: profile target and referral attribution
    # travel together in one signed Telegram start_param.
    code = _code(telegram_id)
    return f"profile_{code}_ref_{code}"


def remix_payload(generation_id: uuid.UUID, referral_telegram_id: int | str | None = None) -> str:
    payload = f"remix_{generation_id}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def prompt_payload(prompt_id: uuid.UUID | str, referral_telegram_id: int | str | None = None) -> str:
    payload = f"prompt_{str(prompt_id).strip()}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def task_payload(task_id: uuid.UUID | str) -> str:
    return f"task_{str(task_id).strip()}"


def _mini_app_short_name() -> str:
    return settings.telegram_mini_app_short_name.strip().strip("/")


def _mini_app_base(username: str) -> str:
    """Build the Main Mini App URL unless a real Direct Mini App short name is set."""

    short_name = _mini_app_short_name()
    if short_name.casefold() in _MAIN_MINI_APP_SHORT_NAME_MARKERS:
        return f"https://t.me/{username}"
    return f"https://t.me/{username}/{quote(short_name, safe='')}"


def mini_app_deep_link(payload: str | None, *, fallback_url: str | None = None) -> str | None:
    """Build a Telegram Mini App URL with a startapp payload.

    Main Mini App links use ``https://t.me/<bot>?startapp=...``. Only a real
    BotFather Direct Mini App short name may become a path segment. ``app`` is
    ROXY's historical deployment placeholder and must not be treated as one.
    """

    username = settings.bot_username.strip().lstrip("@")
    if not username:
        return fallback_url
    base = _mini_app_base(username)
    param = str(payload or "").strip()
    if not param:
        return f"{base}?startapp"
    return f"{base}?startapp={quote(param, safe='_-')}"


def bot_start_link(payload: str | None) -> str | None:
    """Compatibility link for legacy bot /start surfaces; new UI uses startapp."""

    username = settings.bot_username.strip().lstrip("@")
    if not username:
        return None
    param = str(payload or "").strip()
    if not param:
        return f"https://t.me/{username}"
    return f"https://t.me/{username}?start={quote(param, safe='_-')}"


def start_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].split("@", 1)[0] != "/start":
        return None
    payload = parts[1].strip()
    return payload or None


def _profile_link(profile_code: str, referral_code: str | None) -> FeedDeepLink | None:
    effective_referral = referral_code or profile_code
    if profile_code != effective_referral:
        return None
    return FeedDeepLink(
        action="posts",
        profile_referral_code=profile_code,
        referral_telegram_id=int(effective_referral),
    )


def parse_feed_deep_link(payload: str | None) -> FeedDeepLink | None:
    if not payload:
        return None
    if match := _REF_RE.fullmatch(payload):
        return FeedDeepLink(action="ref", referral_telegram_id=int(match.group(1)))
    if match := _POST_RE.fullmatch(payload):
        try:
            generation_id = uuid.UUID(match.group(1))
        except ValueError:
            return None
        referral = int(match.group(2)) if match.group(2) else 0
        return FeedDeepLink(
            action="feed",
            generation_id=generation_id,
            referral_telegram_id=referral,
        )
    if match := _LEGACY_PROFILE_RE.fullmatch(payload):
        return _profile_link(match.group(1), match.group(2))
    if match := _PROFILE_RE.fullmatch(payload):
        return _profile_link(match.group(1), match.group(2))
    if match := _REMIX_RE.fullmatch(payload):
        try:
            generation_id = uuid.UUID(match.group(1))
        except ValueError:
            return None
        referral = int(match.group(2)) if match.group(2) else 0
        return FeedDeepLink(
            action="remix",
            generation_id=generation_id,
            referral_telegram_id=referral,
        )
    return None
