from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

FeedLinkAction = Literal["ref", "feed", "posts", "remix"]

_REF_RE = re.compile(r"^ref_(\d+)$")
_POST_RE = re.compile(r"^feed_([0-9a-fA-F-]{36})_ref_(\d+)$")
_PROFILE_RE = re.compile(r"^posts_(\d+)_ref_(\d+)$")
_REMIX_RE = re.compile(r"^remix_([0-9a-fA-F-]{36})_ref_(\d+)$")


@dataclass(frozen=True, slots=True)
class FeedDeepLink:
    action: FeedLinkAction
    referral_telegram_id: int
    generation_id: uuid.UUID | None = None
    profile_referral_code: str | None = None


def start_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].split("@", 1)[0] != "/start":
        return None
    payload = parts[1].strip()
    return payload or None


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
    if match := _PROFILE_RE.fullmatch(payload):
        return FeedDeepLink(
            action="posts",
            profile_referral_code=match.group(1),
            referral_telegram_id=int(match.group(2)),
        )
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
