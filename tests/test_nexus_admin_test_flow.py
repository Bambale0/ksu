from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.bot.handlers.nexus_test import _is_env_admin
from app.bot.keyboards import QUICK_TEST_TEXT, quick_menu
from app.core.config import settings
from app.providers.nexus import NexusClient, NexusProviderError


def _keyboard_texts(is_admin: bool) -> list[str]:
    markup = quick_menu(is_admin=is_admin)
    return [button.text for row in markup.keyboard for button in row]


def test_test_button_is_visible_only_in_admin_keyboard() -> None:
    assert QUICK_TEST_TEXT not in _keyboard_texts(False)
    assert QUICK_TEST_TEXT in _keyboard_texts(True)


def test_test_flow_uses_env_admin_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "111, 222")
    assert _is_env_admin(111) is True
    assert _is_env_admin(222) is True
    assert _is_env_admin(333) is False
    assert _is_env_admin(None) is False


@pytest.mark.asyncio
async def test_nexus_client_uses_documented_nano_banana_pro_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/generate"
            assert request.headers["Authorization"] == "Bearer test-key"
            assert request.headers["Idempotency-Key"] == "idem-1"
            payload = json.loads(request.content)
            assert payload == {
                "params": {
                    "model_name": "nano-banana-pro",
                    "prompt": "premium product shot",
                    "aspect_ratio": "1:1",
                    "image_size": "2K",
                }
            }
            return httpx.Response(202, json={"task_id": "task-123"})

        assert request.method == "GET"
        assert request.url.path == "/tasks/task-123"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "task_id": "task-123",
                "status": "completed",
                "result": {"image_urls": ["https://cdn.example/result.png"]},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusClient("test-key", client=http_client)
        task_id = await client.create_nano_banana_pro(
            prompt=" premium product shot ",
            idempotency_key="idem-1",
        )
        task = await client.get_task(task_id)

    assert len(requests) == 2
    assert task.task_id == "task-123"
    assert task.status == "completed"
    assert task.image_urls == ["https://cdn.example/result.png"]


def test_nexus_client_fails_closed_without_key() -> None:
    with pytest.raises(NexusProviderError, match="NEXUS_API_KEY"):
        NexusClient("")


def test_nexus_router_is_registered_before_customer_catch_all() -> None:
    dispatcher = Path("app/bot/dispatcher.py").read_text(encoding="utf-8")
    assert "nexus_test.router" in dispatcher
    assert dispatcher.index("include_router(nexus_test.router)") < dispatcher.index(
        "include_router(launcher.router)"
    )


def test_handler_rechecks_env_admin_and_never_hardcodes_secret() -> None:
    source = Path("app/bot/handlers/nexus_test.py").read_text(encoding="utf-8")
    assert "parse_bootstrap_ids" in source
    assert "NEXUS_API_KEY" in source
    assert "NEXUS_API_BASE_URL" in source
    assert "nano-banana-pro" not in source  # model binding lives in provider, not Telegram text
    provider = Path("app/providers/nexus.py").read_text(encoding="utf-8")
    assert '"model_name": "nano-banana-pro"' in provider
    assert "Idempotency-Key" in provider
