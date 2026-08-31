from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_TELEGRAM_INVITE_RE = re.compile(r"^\+[A-Za-z0-9_-]{8,}$")


def _is_valid_telegram_peer(value: str) -> bool:
    return bool(_TELEGRAM_USERNAME_RE.fullmatch(value) or _TELEGRAM_INVITE_RE.fullmatch(value))


def normalize_direct_support_url(raw_url: str | None) -> str | None:
    """Return a safe Telegram support URL or None to use internal support."""

    url = (raw_url or "").strip()
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc.casefold() == "t.me":
        if parsed.params or parsed.query or parsed.fragment:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1:
            return None
        peer = parts[0].lstrip("@")
        if not _is_valid_telegram_peer(peer):
            return None
        return f"https://t.me/{peer}"

    if parsed.scheme == "tg" and parsed.netloc.casefold() == "resolve":
        query = parse_qs(parsed.query)
        domains = query.get("domain") or []
        if len(domains) != 1:
            return None
        peer = domains[0].strip().lstrip("@")
        if not _is_valid_telegram_peer(peer):
            return None
        return f"https://t.me/{peer}"

    return None


def direct_support_handle(raw_url: str | None) -> str | None:
    """Return @username for text messages when direct support is configured."""

    url = normalize_direct_support_url(raw_url)
    if not url:
        return None
    peer = url.rstrip("/").rsplit("/", 1)[-1]
    if peer.startswith("+"):
        return None
    return f"@{peer}"
