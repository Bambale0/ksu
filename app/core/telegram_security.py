from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Telegram WebApp initData is a bearer credential once signed. Signature
# verification alone is not sufficient: a captured payload must expire.
TELEGRAM_INIT_DATA_MAX_AGE = timedelta(hours=24)
TELEGRAM_INIT_DATA_FUTURE_SKEW = timedelta(minutes=5)


def validate_webapp_auth_date(
    auth_date: datetime,
    *,
    now: datetime | None = None,
    max_age: timedelta = TELEGRAM_INIT_DATA_MAX_AGE,
    future_skew: timedelta = TELEGRAM_INIT_DATA_FUTURE_SKEW,
) -> None:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    issued = auth_date
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)
    else:
        issued = issued.astimezone(timezone.utc)

    if issued - current > future_skew:
        raise ValueError("Telegram initData auth_date is in the future")
    if current - issued > max_age:
        raise ValueError("Telegram initData has expired")
