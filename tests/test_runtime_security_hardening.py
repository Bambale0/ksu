from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.metrics import _authorize
from app.core.config import settings
from app.core.telegram_security import (
    TELEGRAM_INIT_DATA_FUTURE_SKEW,
    TELEGRAM_INIT_DATA_MAX_AGE,
    validate_webapp_auth_date,
)
from app.main import _validate_production_security_configuration


def test_telegram_init_data_accepts_fresh_auth_date() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    validate_webapp_auth_date(now - timedelta(minutes=5), now=now)


def test_telegram_init_data_rejects_expired_auth_date() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="expired"):
        validate_webapp_auth_date(now - TELEGRAM_INIT_DATA_MAX_AGE - timedelta(seconds=1), now=now)


def test_telegram_init_data_allows_small_clock_skew() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    validate_webapp_auth_date(now + TELEGRAM_INIT_DATA_FUTURE_SKEW, now=now)


def test_telegram_init_data_rejects_large_future_skew() -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="future"):
        validate_webapp_auth_date(now + TELEGRAM_INIT_DATA_FUTURE_SKEW + timedelta(seconds=1), now=now)


def test_production_webhook_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "telegram_webhook_url", "https://example.test")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")

    with pytest.raises(RuntimeError, match="TELEGRAM_WEBHOOK_SECRET"):
        _validate_production_security_configuration()


def test_nonproduction_webhook_can_run_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "telegram_webhook_url", "https://example.test")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    _validate_production_security_configuration()


def test_production_metrics_fail_closed_without_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "metrics_bearer_token", "")

    with pytest.raises(HTTPException) as exc_info:
        _authorize(None)

    assert exc_info.value.status_code == 503


def test_production_metrics_require_matching_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "metrics_bearer_token", "metrics-secret")

    with pytest.raises(HTTPException) as exc_info:
        _authorize("Bearer wrong")
    assert exc_info.value.status_code == 401

    _authorize("Bearer metrics-secret")
