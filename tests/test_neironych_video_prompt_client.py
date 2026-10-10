from __future__ import annotations

import json

import httpx
import pytest

from app.providers.kie_prompt_tools import PromptToolProviderError
from app.providers.neironych_video_prompt import NeironychVideoPromptClient


@pytest.mark.asyncio
async def test_grok45_video_prompt_uses_responses_with_four_video_frames_and_stable_task_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import neironych_video_prompt as module

    monkeypatch.setattr(module, "_video_bytes", lambda _url: None)
    async def fake_video(_url: str) -> bytes:
        return b"synthetic-video"
    monkeypatch.setattr(module, "_video_bytes", fake_video)
    monkeypatch.setattr(module, "probe_video_duration_seconds", lambda _data: 13.5)

    calls: list[tuple[float, int]] = []
    def frames(_data: bytes, *, duration_seconds: float, max_frames: int) -> list[str]:
        calls.append((duration_seconds, max_frames))
        assert _data == b"synthetic-video"
        return [f"data:image/jpeg;base64,ZmFrZS0{n}" for n in range(max_frames)]
    monkeypatch.setattr(module, "_extract_frame_data_urls_sync", frames)

    payloads: list[dict[str, object]] = []
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["Authorization"] == "Bearer fake-key"
        assert request.headers["Idempotency-Key"] == "ksu-video-prompt-grok45-11111111-1111-4111-8111-111111111111"
        assert request.headers["X-Client-Request-Id"] == "11111111-1111-4111-8111-111111111111"
        data = json.loads(request.content)
        payloads.append(data)
        assert data["model"] == "grok-4.5"
        assert data["stream"] is False
        assert data["reasoning"]["effort"] == "high"
        content = data["input"][1]["content"]
        assert content[0]["type"] == "input_text"
        assert "cinematic focus" in content[0]["text"]
        assert "13.5" in content[0]["text"]
        assert len(content) == 5
        assert all(x["type"] == "input_image" for x in content[1:])
        assert all(x["image_url"].startswith("data:image/jpeg;base64,") for x in content[1:])
        return httpx.Response(200,json={
            "status": "completed",
            "output":[{"type":"message","role":"assistant","content":[
                {"type":"output_text","text":json.dumps({
                    "prompt_ru":"Камера плавно движется",
                    "prompt_en":"A camera moves steadily",
                    "timeline_ru":["начало","конец"],
                },ensure_ascii=False)}
            ]}]
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.xn--e1aikcel5c5a.online") as http_client:
        provider=NeironychVideoPromptClient("fake-key",client=http_client)
        result=await provider.build_video_prompt(
            video_url="https://media.example.test/clip.mp4",
            instruction="cinematic focus",
            duration_seconds=10,
            idempotency_key="11111111-1111-4111-8111-111111111111",
        )
    assert result.model == "grok-4.5"
    assert result.payload["prompt_ru"] == "Камера плавно движется"
    assert result.payload["prompt_en"] == "A camera moves steadily"
    assert result.payload["timeline_ru"] == ["начало","конец"]
    assert len(payloads) == 1 and calls == [(13.5,4)]


@pytest.mark.asyncio
async def test_grok45_responses_503_is_single_submitted_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import neironych_video_prompt as module

    async def fake_video(_url: str) -> bytes:
        return b"synthetic-video"
    monkeypatch.setattr(module, "_video_bytes", fake_video)
    monkeypatch.setattr(module, "probe_video_duration_seconds", lambda _data: 8.0)
    monkeypatch.setattr(
        module, "_extract_frame_data_urls_sync",
        lambda _data, *, duration_seconds, max_frames: ["data:image/jpeg;base64,eA=="],
    )
    seen=[]
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Idempotency-Key"])
        return httpx.Response(503,json={"detail":"temporarily unavailable"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.xn--e1aikcel5c5a.online") as http_client:
        provider=NeironychVideoPromptClient("fake-key",client=http_client)
        with pytest.raises(PromptToolProviderError,match="Grok 4.5"):
            await provider.build_video_prompt(
                video_url="https://media.example.test/clip.mp4",
                idempotency_key="11111111-1111-4111-8111-111111111111",
            )
    assert len(seen)==1


@pytest.mark.asyncio
async def test_grok45_incomplete_responses_cannot_be_marked_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers import neironych_video_prompt as module
    async def fake_video(_url: str) -> bytes:
        return b"synthetic-video"
    monkeypatch.setattr(module, "_video_bytes", fake_video)
    monkeypatch.setattr(module, "probe_video_duration_seconds", lambda _data: 8.0)
    monkeypatch.setattr(
        module, "_extract_frame_data_urls_sync",
        lambda _data, *, duration_seconds, max_frames: ["data:image/jpeg;base64,eA=="],
    )
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200,json={"status":"incomplete", "output":[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.xn--e1aikcel5c5a.online") as http_client:
        provider=NeironychVideoPromptClient("fake-key",client=http_client)
        with pytest.raises(PromptToolProviderError,match="incomplete"):
            await provider.build_video_prompt(
                video_url="https://media.example.test/clip.mp4",
                idempotency_key="11111111-1111-4111-8111-111111111111",
            )
