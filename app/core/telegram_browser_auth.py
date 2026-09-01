from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

TELEGRAM_LOGIN_MAX_AGE = timedelta(minutes=10)
TELEGRAM_LOGIN_FUTURE_SKEW = timedelta(minutes=1)

_ALLOWED_LOGIN_FIELDS = {
    "id",
    "first_name",
    "last_name",
    "username",
    "photo_url",
    "auth_date",
}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _normalized_login_payload(raw: Mapping[str, Any]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in _ALLOWED_LOGIN_FIELDS | {"hash"}:
        value = raw.get(key)
        if value is not None:
            payload[key] = str(value)
    return payload


def verify_telegram_login_widget(
    raw: Mapping[str, Any],
    bot_token: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify Telegram Login Widget data and return a normalized WebApp user."""

    if not bot_token:
        raise ValueError("Telegram bot is not configured")

    payload = _normalized_login_payload(raw)
    received_hash = payload.pop("hash", "")
    if not received_hash:
        raise ValueError("Missing Telegram login signature")

    try:
        telegram_id = int(payload.get("id", "0"))
        auth_date = datetime.fromtimestamp(int(payload.get("auth_date", "0")), tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("Invalid Telegram login payload") from exc

    current = _utc(now)
    if telegram_id <= 0:
        raise ValueError("Invalid Telegram login payload")
    if auth_date - current > TELEGRAM_LOGIN_FUTURE_SKEW:
        raise ValueError("Telegram login auth_date is in the future")
    if current - auth_date > TELEGRAM_LOGIN_MAX_AGE:
        raise ValueError("Telegram login has expired")

    data_check_string = "\n".join(
        f"{key}={payload[key]}" for key in sorted(payload) if key in _ALLOWED_LOGIN_FIELDS
    )
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram login signature")

    first_name = payload.get("first_name", "").strip()
    if not first_name:
        raise ValueError("Telegram first_name is missing")

    return {
        "id": telegram_id,
        "first_name": first_name,
        "last_name": payload.get("last_name", ""),
        "username": payload.get("username", ""),
        "photo_url": payload.get("photo_url", ""),
        "language_code": "ru",
    }


def build_browser_init_data(
    user: Mapping[str, Any],
    bot_token: str,
    *,
    now: datetime | None = None,
) -> str:
    """Create standard signed WebApp initData for the existing KSU auth dependency."""

    if not bot_token:
        raise ValueError("Telegram bot is not configured")

    current = _utc(now)
    fields = {
        "auth_date": str(int(current.timestamp())),
        "query_id": f"browser_{secrets.token_urlsafe(18)}",
        "user": json.dumps(dict(user), ensure_ascii=False, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(fields)
