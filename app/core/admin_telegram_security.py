from __future__ import annotations

from datetime import datetime, timedelta

from aiogram.utils.web_app import safe_parse_webapp_init_data

from app.core.config import settings
from app.core.telegram_security import validate_webapp_auth_date

ADMIN_TELEGRAM_INIT_DATA_MAX_AGE = timedelta(minutes=10)
ADMIN_TELEGRAM_INIT_DATA_FUTURE_SKEW = timedelta(minutes=1)
FRESH_ADMIN_INIT_DATA_PATHS = frozenset(
    {
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/mfa/setup",
        "/api/v1/admin/auth/step-up",
    }
)


def validate_fresh_admin_init_data(
    raw: str,
    *,
    now: datetime | None = None,
) -> None:
    """Reject replayed Telegram credentials before privilege establishment."""

    if not settings.bot_token or not raw:
        raise ValueError("Admin Telegram initData is not configured")
    init_data = safe_parse_webapp_init_data(settings.bot_token, raw)
    auth_date = getattr(init_data, "auth_date", None)
    if auth_date is None or getattr(init_data, "user", None) is None:
        raise ValueError("Admin Telegram initData is incomplete")
    validate_webapp_auth_date(
        auth_date,
        now=now,
        max_age=ADMIN_TELEGRAM_INIT_DATA_MAX_AGE,
        future_skew=ADMIN_TELEGRAM_INIT_DATA_FUTURE_SKEW,
    )
