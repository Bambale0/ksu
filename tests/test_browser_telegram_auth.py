from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from aiogram.utils.web_app import safe_parse_webapp_init_data

from app.core.telegram_browser_auth import (
    build_browser_init_data,
    verify_telegram_login_widget,
)

BOT_TOKEN = "123456:browser-auth-test-token"


def _signed_login_payload(*, auth_date: datetime | None = None) -> dict[str, object]:
    issued = auth_date or datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "id": 424242,
        "first_name": "Roxy",
        "last_name": "Creator",
        "username": "roxy_creator",
        "photo_url": "https://example.test/avatar.jpg",
        "auth_date": int(issued.timestamp()),
    }
    check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret = hashlib.sha256(BOT_TOKEN.encode("utf-8")).digest()
    payload["hash"] = hmac.new(
        secret,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return payload


def test_browser_login_widget_signature_is_verified() -> None:
    payload = _signed_login_payload()

    user = verify_telegram_login_widget(payload, BOT_TOKEN)

    assert user == {
        "id": 424242,
        "first_name": "Roxy",
        "last_name": "Creator",
        "username": "roxy_creator",
        "photo_url": "https://example.test/avatar.jpg",
        "language_code": "ru",
    }


def test_browser_login_widget_rejects_tampered_identity() -> None:
    payload = _signed_login_payload()
    payload["id"] = 777777

    with pytest.raises(ValueError, match="signature"):
        verify_telegram_login_widget(payload, BOT_TOKEN)


def test_browser_login_widget_rejects_stale_payload() -> None:
    payload = _signed_login_payload(
        auth_date=datetime.now(timezone.utc) - timedelta(minutes=11),
    )

    with pytest.raises(ValueError, match="expired"):
        verify_telegram_login_widget(payload, BOT_TOKEN)


def test_browser_init_data_enters_existing_webapp_auth_contour() -> None:
    user = verify_telegram_login_widget(_signed_login_payload(), BOT_TOKEN)

    init_data = build_browser_init_data(user, BOT_TOKEN)
    parsed = safe_parse_webapp_init_data(BOT_TOKEN, init_data)

    assert parsed.user is not None
    assert parsed.user.id == 424242
    assert parsed.user.first_name == "Roxy"
    assert str(parsed.query_id).startswith("browser_")
    assert parse_qs(init_data)["auth_date"]


def test_mini_app_browser_auth_reuses_same_frontend_and_headers() -> None:
    root = Path(__file__).resolve().parents[1]
    boundary = (root / "frontend/mini-app/components/telegram-auth-boundary.tsx").read_text(encoding="utf-8")
    gate = (root / "frontend/mini-app/components/telegram-browser-login.tsx").read_text(encoding="utf-8")
    telegram = (root / "frontend/mini-app/lib/telegram.ts").read_text(encoding="utf-8")
    layout = (root / "frontend/mini-app/app/layout.tsx").read_text(encoding="utf-8")
    social = (root / "frontend/mini-app/components/roxy-social-app.tsx").read_text(encoding="utf-8")
    action = (root / "frontend/mini-app/components/generation-action-app.tsx").read_text(encoding="utf-8")

    assert "TelegramBrowserLogin" in boundary
    assert "getInitDataFallback" in boundary
    assert "<TelegramAuthBoundary>{children}</TelegramAuthBoundary>" in layout
    assert "/api/v1/browser-auth/config" in gate
    assert "/api/v1/browser-auth" in gate
    assert "telegram-widget.js" in gate
    assert "tgWebAppData" in gate
    assert "localStorage" not in gate
    assert "__roxy_browser_init_data_v1" in gate
    assert "__roxy_browser_init_data_v1" in layout

    assert 'headers["X-Telegram-Init-Data"] = initData' in telegram
    assert "const recoveredInitData = getInitDataFallback();" in telegram
    assert "tg.initData = recoveredInitData" in telegram
    assert "telegram-web-app.js" in layout
    assert "const tg = initTelegram();" in social
    assert "tg?.initData ? api.me()" in social
    assert "const tg = initTelegram();" in action
