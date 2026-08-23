from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings

FeedLinkAction = Literal["ref", "feed", "posts", "remix"]

_REF_RE = re.compile(r"^ref_(\d+)$")
_POST_RE = re.compile(r"^feed_([0-9a-fA-F-]{36})_ref_(\d+)$")
_LEGACY_PROFILE_RE = re.compile(r"^posts_(\d+)_ref_(\d+)$")
_PROFILE_RE = re.compile(r"^profile_(\d+)(?:_ref_(\d+))?$")
_REMIX_RE = re.compile(r"^remix_([0-9a-fA-F-]{36})_ref_(\d+)$")
_STARTAPP_RE = re.compile(r"^[A-Za-z0-9_-]{1,512}$")


@dataclass(frozen=True, slots=True)
class FeedDeepLink:
    action: FeedLinkAction
    referral_telegram_id: int
    generation_id: uuid.UUID | None = None
    profile_referral_code: str | None = None


def referral_payload(telegram_id: int) -> str:
    return f"ref_{telegram_id}"


def post_payload(generation_id: uuid.UUID, referral_telegram_id: int | str) -> str:
    return f"feed_{generation_id}_ref_{referral_telegram_id}"


def profile_payload(telegram_id: int | str) -> str:
    return f"profile_{telegram_id}"


def remix_payload(generation_id: uuid.UUID, referral_telegram_id: int | str) -> str:
    return f"remix_{generation_id}_ref_{referral_telegram_id}"


def mini_app_deep_link(payload: str | None) -> str | None:
    """Build a Telegram Main Mini App link carrying a signed startapp payload.

    Telegram passes ``startapp`` to the Mini App as ``start_param`` inside signed
    initData. That lets the backend validate referral attribution while the user
    lands directly in ROXY instead of first opening the bot chat.
    """

    if not payload or not _STARTAPP_RE.fullmatch(payload):
        return None
    username = settings.bot_username.strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}?startapp={payload}"


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
        return FeedDeepLink(
            action="feed",
            generation_id=generation_id,
            referral_telegram_id=int(match.group(2)),
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
        return FeedDeepLink(
            action="remix",
            generation_id=generation_id,
            referral_telegram_id=int(match.group(2)),
        )
    return None
