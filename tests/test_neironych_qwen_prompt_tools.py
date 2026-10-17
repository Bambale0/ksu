from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.kie_prompt_tools import PromptToolProviderError
from app.providers.neironych_qwen_prompt_tools import NeironychQwenPromptToolsClient


def _chat_response(result: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "chatcmpl-test", "choices": [
            {"index": 0, "message": {"role": "assistant",
                                     "content": json.dumps(result, ensure_ascii=False)}}
        ]
    })


@pytest.mark.asyncio
async def test_photo_prompt_qwen_uses_chat_multimodal_with_fixed_idempotency() -> None:
    requests: list[dict] = []
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-token"
        assert request.headers["Idempotency-Key"] == (
            "ksu-prompt-photo-qwen38-11111111-1111-4111-8111-111111111111"
        )
        assert request.headers["X-Client-Request-Id"] == "11111111-1111-4111-8111-111111111111"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "qwen3.8-max"
        assert payload["stream"] is False
        content = payload["messages"][1]["content"]
        assert content[0]["type"] == "text"
        assert "change lighting" in content[0]["text"]
        assert content[1] == {
            "type": "image_url",
            "image_url": {"url": "https://cdn.example.test/reference.jpg"},
        }
        assert "photorealistic" in payload["messages"][0]["content"]
        return _chat_response({
            "prompt_ru": "Фотография в студии",
            "prompt_en": "Studio photo",
            "negative_prompt": "distortion",
            "key_details": ["one", "two", "three"],
        })

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as client:
        adapter = NeironychQwenPromptToolsClient("synthetic-token", client=client)
        result = await adapter.analyze_image(
            image_url="https://cdn.example.test/reference.jpg",
            instruction="change lighting",
            idempotency_key="11111111-1111-4111-8111-111111111111",
        )
    assert len(requests) == 1
    assert result.model == "qwen3.8-max"
    assert result.payload["prompt_ru"] == "Фотография в студии"
    assert result.payload["prompt_en"] == "Studio photo"


@pytest.mark.asyncio
async def test_video_prompt_qwen_uses_four_jpeg_frames_and_real_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import neironych_qwen_prompt_tools as module
    async def video(_url: str) -> bytes:
        return b"synthetic-source"
    monkeypatch.setattr(module, "_video_bytes", video)
    monkeypatch.setattr(module, "probe_video_duration_seconds", lambda _v: 9.5)
    extract = AsyncMock(return_value=None)
    del extract
    frame_calls = []
    def frames(_data: bytes, *, duration_seconds: float, max_frames: int) -> list[str]:
        frame_calls.append((duration_seconds, max_frames))
        return ["data:image/jpeg;base64,ZmFrZQ==" for _ in range(max_frames)]
    monkeypatch.setattr(module, "_extract_frame_data_urls_sync", frames)
    submitted: list[dict] = []
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotency-Key"] == (
            "ksu-prompt-video-qwen38-22222222-2222-4222-8222-222222222222"
        )
        body = json.loads(request.content)
        submitted.append(body)
        assert body["model"] == "qwen3.8-max"
        content = body["messages"][1]["content"]
        assert content[0]["type"] == "text"
        assert "9.5" in content[0]["text"]
        assert "cinematic" in content[0]["text"]
        assert len(content) == 5
        assert [x["type"] for x in content[1:]] == ["image_url"] * 4
        assert all(x["image_url"]["url"].startswith("data:image/jpeg;base64,") for x in content[1:])
        return _chat_response({
            "prompt_ru": "Камера следует за автомобилем",
            "prompt_en": "A camera tracks a vehicle",
            "timeline_ru": ["въезд", "поворот", "выезд"],
            "camera_movement_ru": "следящая камера",
        })
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as client:
        adapter = NeironychQwenPromptToolsClient("synthetic-token", client=client)
        result = await adapter.build_video_prompt(
            video_url="https://media.example.test/video.mp4",
            instruction="cinematic",
            duration_seconds=10,
            idempotency_key="22222222-2222-4222-8222-222222222222",
        )
    assert len(submitted) == 1 and frame_calls == [(9.5, 4)]
    assert result.model == "qwen3.8-max"
    assert result.payload["prompt_ru"] == "Камера следует за автомобилем"
    assert result.payload["timeline_ru"] == ["въезд", "поворот", "выезд"]


@pytest.mark.asyncio
async def test_qwen_insufficient_balance_never_retries_paid_post() -> None:
    requests: list[httpx.Request] = []
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(402, json={"error": {"code": "insufficient_balance"}})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as client:
        adapter = NeironychQwenPromptToolsClient("synthetic-token", client=client)
        with pytest.raises(PromptToolProviderError, match="Qwen"):
            await adapter.analyze_image(
                image_url="https://cdn.example.test/photo.jpg",
                idempotency_key="11111111-1111-4111-8111-111111111111",
            )
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_qwen_rejects_incomplete_photo_instead_of_marking_success() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: _chat_response({"prompt_ru":"Привет"})),
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as client:
        adapter = NeironychQwenPromptToolsClient("synthetic-token", client=client)
        with pytest.raises(PromptToolProviderError, match="Qwen"):
            await adapter.analyze_image(
                image_url="https://cdn.example.test/photo.jpg",
                idempotency_key="11111111-1111-4111-8111-111111111111",
            )


@pytest.mark.asyncio
async def test_qwen_rejects_invalid_task_key_before_any_network() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: (_ for _ in ()).throw(AssertionError("paid request"))),
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as client:
        adapter = NeironychQwenPromptToolsClient("synthetic-token", client=client)
        with pytest.raises(PromptToolProviderError, match="UUID"):
            await adapter.analyze_image(
                image_url="https://cdn.example.test/photo.jpg",
                idempotency_key="bad-id",
            )
