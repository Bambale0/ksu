from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from app.core.config import settings

FeedLinkAction = Literal["ref", "feed", "posts", "remix", "trend"]

_REF_RE = re.compile(r"^ref_(\d+)$", re.IGNORECASE)
_POST_RE = re.compile(r"^feed_([0-9a-fA-F-]{36})(?:_ref_(\d+))?$", re.IGNORECASE)
_LEGACY_PROFILE_RE = re.compile(r"^posts_(\d+)_ref_(\d+)$", re.IGNORECASE)
_PROFILE_RE = re.compile(r"^profile_(\d+)(?:_ref_(\d+))?$", re.IGNORECASE)
_REMIX_RE = re.compile(r"^remix_([0-9a-fA-F-]{36})(?:_ref_(\d+))?$", re.IGNORECASE)
_TREND_RE = re.compile(r"^trend_([0-9a-fA-F-]{36})(?:_ref_(\d+))?$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FeedDeepLink:
    action: FeedLinkAction
    referral_telegram_id: int
    generation_id: uuid.UUID | None = None
    profile_referral_code: str | None = None
    trend_id: uuid.UUID | None = None


def _code(value: int | str) -> str:
    return str(value).strip().upper()


def _clean_bot_username(value: str | None) -> str:
    return str(value or "").strip().lstrip("@")


def referral_payload(telegram_id: int | str) -> str:
    return f"ref_{_code(telegram_id)}"


def post_payload(generation_id: uuid.UUID, referral_telegram_id: int | str | None = None) -> str:
    payload = f"feed_{generation_id}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def profile_payload(telegram_id: int | str) -> str:
    code = _code(telegram_id)
    return f"profile_{code}_ref_{code}"


def remix_payload(generation_id: uuid.UUID, referral_telegram_id: int | str | None = None) -> str:
    payload = f"remix_{generation_id}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def trend_payload(
    trend_id: uuid.UUID | str,
    referral_telegram_id: int | str | None = None,
) -> str:
    """Build a public trend payload, optionally attributed to the user sharing it."""

    payload = f"trend_{str(trend_id).strip()}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def prompt_payload(prompt_id: uuid.UUID | str, referral_telegram_id: int | str | None = None) -> str:
    payload = f"prompt_{str(prompt_id).strip()}"
    code = _code(referral_telegram_id) if referral_telegram_id is not None else ""
    return f"{payload}_ref_{code}" if code else payload


def task_payload(task_id: uuid.UUID | str) -> str:
    return f"task_{str(task_id).strip()}"


def mini_app_deep_link(
    payload: str | None,
    *,
    fallback_url: str | None = None,
    bot_username: str | None = None,
) -> str | None:
    """Build the canonical Telegram Main Mini App link used by tanyapi.

    Public repeat, feed, profile and referral links must open ROXY immediately,
    without landing in the bot chat first. Telegram's Main Mini App deep-link
    syntax is ``https://t.me/<bot>?startapp=<payload>`` and does not depend on a
    named Mini App short name. ``fallback_url`` is only used when the bot
    username itself is unavailable.
    """

    username = _clean_bot_username(bot_username or settings.bot_username)
    if not username:
        return fallback_url
    param = str(payload or "").strip()
    if not param:
        return f"https://t.me/{username}?startapp"
    return f"https://t.me/{username}?startapp={quote(param, safe='_-')}"


def bot_start_link(payload: str | None, *, bot_username: str | None = None) -> str | None:
    """Compatibility link for legacy bot /start surfaces."""

    username = _clean_bot_username(bot_username or settings.bot_username)
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
    if match := _TREND_RE.fullmatch(payload):
        try:
            trend_id = uuid.UUID(match.group(1))
        except ValueError:
            return None
        referral = int(match.group(2)) if match.group(2) else 0
        return FeedDeepLink(
            action="trend",
            trend_id=trend_id,
            referral_telegram_id=referral,
        )
    return None
