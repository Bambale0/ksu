from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.health import OPERATIONAL_WORKERS
from app.core.config import settings
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_operational_health_covers_every_production_worker() -> None:
    assert set(OPERATIONAL_WORKERS) == {
        "generation-worker",
        "payment-worker",
        "media-worker",
        "prompt-tool-worker",
        "notification-worker",
        "admin-support-worker",
        "admin-campaign-worker",
        "creator-partnership-worker",
        "kie-credit-alert-worker",
    }


def test_delivery_worker_heartbeats_are_tied_to_worker_progress() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "python -m app.workers.heartbeat" not in compose

    workers = (
        (
            "notification-worker",
            "app.workers.notifications",
            "app/workers/notifications.py",
            "await _process_delivery(bot, delivery_id)",
        ),
        (
            "admin-support-worker",
            "app.workers.admin_support",
            "app/workers/admin_support.py",
            "await _process(bot, outbox_id)",
        ),
        (
            "admin-campaign-worker",
            "app.workers.admin_campaigns",
            "app/workers/admin_campaigns.py",
            "await _process(bot, delivery_id)",
        ),
    )

    for worker_name, module_name, source_path, process_call in workers:
        assert f"command: python -m {module_name}" in compose
        source = (ROOT / source_path).read_text(encoding="utf-8")
        assert f'WORKER_NAME = "{worker_name}"' in source
        assert "record_worker_heartbeat" in source
        run_block = source.split("async def run() -> None:", 1)[1]
        assert process_call in run_block
        # One heartbeat before claiming work keeps an idle worker healthy; the
        # second, after each processed row, proves health advances with progress.
        assert run_block.count("await _heartbeat(redis)") >= 2


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
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    monkeypatch.setattr(app.state, "bot_has_main_web_app", True, raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/telegram")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "bot_configured": True,
        "bot_username": "roxy_aicreativebot",
        "mini_app_short_name": "app",
        "direct_mini_app_link_template": "https://t.me/roxy_aicreativebot?startapp=<payload>",
        "named_mini_app_link_template": "https://t.me/roxy_aicreativebot/app?startapp=<payload>",
        "bot_start_link_template": "https://t.me/roxy_aicreativebot?start=<payload>",
        "main_mini_app_enabled": True,
        "main_mini_app_link_template": "https://t.me/roxy_aicreativebot?startapp=<payload>",
    }


@pytest.mark.asyncio
async def test_telegram_health_keeps_main_link_canonical_when_named_app_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "bot_username", "@roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    monkeypatch.setattr(app.state, "bot_has_main_web_app", False, raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/telegram")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["bot_username"] == "roxy_aicreativebot"
    assert payload["mini_app_short_name"] == "app"
    assert payload["direct_mini_app_link_template"] == (
        "https://t.me/roxy_aicreativebot?startapp=<payload>"
    )
    assert payload["named_mini_app_link_template"] == (
        "https://t.me/roxy_aicreativebot/app?startapp=<payload>"
    )
    assert payload["bot_start_link_template"] == (
        "https://t.me/roxy_aicreativebot?start=<payload>"
    )
    assert payload["main_mini_app_enabled"] is False
    assert payload["main_mini_app_link_template"] == (
        "https://t.me/roxy_aicreativebot?startapp=<payload>"
    )


@pytest.mark.asyncio
async def test_telegram_health_does_not_require_direct_mini_app_short_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "bot_username", "@roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "")
    monkeypatch.setattr(app.state, "bot_has_main_web_app", True, raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/telegram")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mini_app_short_name"] is None
    assert payload["direct_mini_app_link_template"] == (
        "https://t.me/roxy_aicreativebot?startapp=<payload>"
    )
    assert payload["named_mini_app_link_template"] is None
    assert payload["bot_start_link_template"] == (
        "https://t.me/roxy_aicreativebot?start=<payload>"
    )
