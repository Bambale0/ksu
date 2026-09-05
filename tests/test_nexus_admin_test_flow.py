from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.bot.handlers.nexus_test import (
    NEXUS_TEST_ASPECT_RATIOS,
    NEXUS_TEST_IMAGE_SIZES,
    _aspect_ratio_keyboard,
    _data_url,
    _image_size_keyboard,
    _is_env_admin,
    _references_keyboard,
)
from app.bot.keyboards import QUICK_TEST_TEXT, quick_menu
from app.core.config import settings
from app.providers.nexus import (
    NANO_BANANA_PRO_ASPECT_RATIOS,
    NANO_BANANA_PRO_MAX_REFERENCES,
    NexusClient,
    NexusProviderError,
)


def _keyboard_texts(is_admin: bool) -> list[str]:
    markup = quick_menu(is_admin=is_admin)
    return [button.text for row in markup.keyboard for button in row]


def _inline_callbacks(markup) -> list[str]:
    return [str(button.callback_data or "") for row in markup.inline_keyboard for button in row]


def test_test_button_is_visible_only_in_admin_keyboard() -> None:
    assert QUICK_TEST_TEXT not in _keyboard_texts(False)
    assert QUICK_TEST_TEXT in _keyboard_texts(True)


def test_test_flow_uses_env_admin_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "111, 222")
    assert _is_env_admin(111) is True
    assert _is_env_admin(222) is True
    assert _is_env_admin(333) is False
    assert _is_env_admin(None) is False


def test_reference_step_requires_at_least_one_image_before_continue() -> None:
    assert "nexus-test:refs:done" not in _inline_callbacks(_references_keyboard(0))
    assert "nexus-test:refs:done" in _inline_callbacks(_references_keyboard(1))
    assert NANO_BANANA_PRO_MAX_REFERENCES == 4


def test_admin_test_exposes_full_aspect_ratio_and_only_2k_4k_quality_choices() -> None:
    ratio_callbacks = _inline_callbacks(_aspect_ratio_keyboard())
    for ratio in NEXUS_TEST_ASPECT_RATIOS:
        assert f"nexus-test:ratio:{ratio}" in ratio_callbacks
        assert ratio in NANO_BANANA_PRO_ASPECT_RATIOS
    assert NEXUS_TEST_ASPECT_RATIOS == (
        "auto",
        "1:1",
        "4:3",
        "3:4",
        "3:2",
        "2:3",
        "5:4",
        "4:5",
        "16:9",
        "9:16",
        "21:9",
    )

    size_callbacks = _inline_callbacks(_image_size_keyboard())
    assert NEXUS_TEST_IMAGE_SIZES == ("2K", "4K")
    assert "nexus-test:size:2K" in size_callbacks
    assert "nexus-test:size:4K" in size_callbacks
    assert "nexus-test:size:1K" not in size_callbacks


def test_telegram_reference_is_encoded_as_data_url_for_nexus() -> None:
    assert _data_url(b"abc", "image/jpeg") == "data:image/jpeg;base64,YWJj"


@pytest.mark.asyncio
async def test_nexus_client_uses_reference_4k_and_aspect_ratio_contract() -> None:
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
                    "prompt": "keep the person, change the scene",
                    "aspect_ratio": "9:16",
                    "image_size": "4K",
                    "image_urls": [
                        "data:image/jpeg;base64,cmVmMQ==",
                        "data:image/png;base64,cmVmMg==",
                    ],
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
            prompt=" keep the person, change the scene ",
            image_urls=[
                "data:image/jpeg;base64,cmVmMQ==",
                "data:image/png;base64,cmVmMg==",
            ],
            aspect_ratio="9:16",
            image_size="4K",
            idempotency_key="idem-1",
        )
        task = await client.get_task(task_id)

    assert len(requests) == 2
    assert task.task_id == "task-123"
    assert task.status == "completed"
    assert task.image_urls == ["https://cdn.example/result.png"]


@pytest.mark.asyncio
async def test_nexus_client_accepts_four_references_and_rejects_five() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"task_id": "task-four"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://nexusapi.dev") as http_client:
        client = NexusClient("test-key", client=http_client)
        await client.create_nano_banana_pro(
            prompt="four refs",
            image_urls=[f"https://example.test/ref-{index}.jpg" for index in range(4)],
            image_size="2K",
            aspect_ratio="1:1",
        )
        with pytest.raises(NexusProviderError, match="at most 4 references"):
            await client.create_nano_banana_pro(
                prompt="five refs",
                image_urls=[f"https://example.test/ref-{index}.jpg" for index in range(5)],
            )

    params = captured["params"]
    assert isinstance(params, dict)
    assert len(params["image_urls"]) == 4


def test_nexus_client_fails_closed_without_key() -> None:
    with pytest.raises(NexusProviderError, match="NEXUS_API_KEY"):
        NexusClient("")


def test_nexus_router_is_registered_before_customer_catch_all() -> None:
    dispatcher = Path("app/bot/dispatcher.py").read_text(encoding="utf-8")
    assert "nexus_test.router" in dispatcher
    assert dispatcher.index("include_router(nexus_test.router)") < dispatcher.index(
        "include_router(launcher.router)"
    )


def test_handler_rechecks_env_admin_and_reads_secret_from_env() -> None:
    source = Path("app/bot/handlers/nexus_test.py").read_text(encoding="utf-8")
    assert "parse_bootstrap_ids" in source
    assert 'os.environ.get("NEXUS_API_KEY"' in source
    assert 'os.environ.get("NEXUS_API_BASE_URL"' in source
    assert "NexusTestStates.references" in source
    assert "NexusTestStates.aspect_ratio" in source
    assert "NexusTestStates.image_size" in source
    assert "image_urls=image_urls" in source
    assert "image_size=image_size" in source
    assert "aspect_ratio=aspect_ratio" in source
    assert "timeout_seconds=240" in source

    provider = Path("app/providers/nexus.py").read_text(encoding="utf-8")
    assert '"model_name": "nano-banana-pro"' in provider
    assert 'params["image_urls"] = references' in provider
    assert "Idempotency-Key" in provider
