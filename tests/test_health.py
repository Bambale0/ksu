import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_live() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_telegram_health_reports_main_mini_app_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(app.state, "bot_has_main_web_app", True, raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/telegram")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "bot_configured": True,
        "bot_username": "roxy_aicreativebot",
        "main_mini_app_enabled": True,
        "main_mini_app_link_template": "https://t.me/roxy_aicreativebot?startapp=<payload>",
    }


@pytest.mark.asyncio
async def test_telegram_health_surfaces_botfather_misconfiguration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "bot_username", "@roxy_aicreativebot")
    monkeypatch.setattr(app.state, "bot_has_main_web_app", False, raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/telegram")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "misconfigured"
    assert payload["bot_username"] == "roxy_aicreativebot"
    assert payload["main_mini_app_enabled"] is False
    assert payload["main_mini_app_link_template"] == (
        "https://t.me/roxy_aicreativebot?startapp=<payload>"
    )
