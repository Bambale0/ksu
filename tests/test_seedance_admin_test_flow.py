from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.bot.handlers.seedance_test import _model_keyboard
from app.providers.neironych_video import (
    NeironychProviderError,
    NeironychVideoClient,
    SEEDANCE_TEST_MODELS,
    is_failure_status,
    is_success_status,
)


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def test_admin_test_model_picker_exposes_nano_and_both_seedance_versions() -> None:
    callbacks = _callbacks(_model_keyboard())
    assert "nexus-test:model:nano-banana-pro" in callbacks
    assert "nexus-test:model:seedance-2" in callbacks
    assert "nexus-test:model:seedance-2.5" in callbacks
    assert SEEDANCE_TEST_MODELS == ("seedance-2", "seedance-2.5")


@pytest.mark.asyncio
async def test_seedance_client_uses_documented_async_video_contract_and_raw_passthrough(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer secret"

        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": "seedance-2"}, {"id": "seedance-2.5"}]},
            )
        if request.method == "POST":
            assert request.url.path == "/v1/videos/generations"
            assert request.headers["Idempotency-Key"] == "ksu-test-12345678"
            payload = json.loads(request.content)
            assert payload == {
                "model": "seedance-2.5",
                "prompt": "cinematic",
                "duration": 12,
                "aspect_ratio": "9:16",
                "provider_future_option": {"enabled": True},
            }
            return httpx.Response(202, json={"request_id": "video-123"})
        if request.url.path == "/v1/videos/video-123/content":
            return httpx.Response(200, content=b"fake-mp4", headers={"content-type": "video/mp4"})

        assert request.url.path == "/v1/videos/video-123"
        return httpx.Response(
            200,
            json={"request_id": "video-123", "status": "completed"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient(
            "secret",
            "https://provider.example",
            client=http_client,
        )
        assert await client.list_models() == ["seedance-2", "seedance-2.5"]
        request_id = await client.create_video(
            model="seedance-2.5",
            payload={
                "model": "attempted-override",
                "prompt": "cinematic",
                "duration": 12,
                "aspect_ratio": "9:16",
                "provider_future_option": {"enabled": True},
            },
            idempotency_key="ksu-test-12345678",
        )
        assert request_id == "video-123"
        status, error, _payload = await client.get_video(request_id)
        assert status == "completed"
        assert error == ""

        target = tmp_path / "result.mp4"
        content_type = await client.download_content_to(
            request_id,
            target,
            max_bytes=1024,
        )

    assert content_type == "video/mp4"
    assert target.read_bytes() == b"fake-mp4"
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_seedance_client_rejects_unsupported_model_and_short_idempotency_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient("secret", "https://provider.example", client=http_client)
        with pytest.raises(NeironychProviderError, match="Unsupported"):
            await client.create_video(
                model="other",
                payload={"prompt": "x"},
                idempotency_key="12345678",
            )
        with pytest.raises(NeironychProviderError, match="8..160"):
            await client.create_video(
                model="seedance-2",
                payload={"prompt": "x"},
                idempotency_key="short",
            )


@pytest.mark.asyncio
async def test_seedance_provider_error_is_bounded_and_redacts_long_tokens() -> None:
    secret = "a" * 64

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"message": f"bad media https://cdn.example/file?token={secret}"}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient("secret", "https://provider.example", client=http_client)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_video(
                model="seedance-2",
                payload={"prompt": "x"},
                idempotency_key="12345678-valid",
            )

    assert caught.value.status_code == 422
    assert secret not in str(caught.value)
    assert "[REDACTED]" in str(caught.value)


def test_seedance_status_normalization() -> None:
    assert is_success_status("completed")
    assert is_success_status("DONE")
    assert is_failure_status("failed")
    assert is_failure_status("cancelled")
    assert not is_success_status("processing")
    assert not is_failure_status("queued")


def test_seedance_test_is_durable_and_registered_before_customer_router() -> None:
    dispatcher = Path("app/bot/dispatcher.py").read_text(encoding="utf-8")
    assert "seedance_test.router" in dispatcher
    assert dispatcher.index("include_router(seedance_test.router)") < dispatcher.index(
        "include_router(launcher.router)"
    )

    handler = Path("app/bot/handlers/seedance_test.py").read_text(encoding="utf-8")
    assert "SeedanceAdminTaskService.enqueue" in handler
    assert "NEIRONYCH_API_KEY" in handler
    assert "json.loads" in handler
    assert 'payload["model"] = model_name' in handler
    assert 'payload["prompt"] = prompt' in handler

    worker = Path("app/workers/nexus_test.py").read_text(encoding="utf-8")
    assert "SeedanceAdminTaskService.claim" in worker
    assert "SeedanceAdminTaskService.process" in worker

    service = Path("app/services/seedance_admin_tasks.py").read_text(encoding="utf-8")
    assert "client.list_models()" in service
    assert "client.create_video(" in service
    assert "client.get_video(" in service
    assert "client.download_content_to(" in service
