from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers import tanyapi_video_prompt as video_provider
from app.providers.kie_prompt_tools import (
    KiePromptToolsClient,
    PromptToolProviderError,
    PromptToolProviderResult,
)
from app.services import prompt_tools as prompt_module
from app.services import tanyapi_prompt_contract as prompt_contract
from app.services import video_prompt_media


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.content = b""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.kie.ai/codex/v1/responses")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.posts: list[dict] = []

    async def post(self, path: str, *, json: dict, timeout: float) -> _Response:
        assert path == "/codex/v1/responses"
        assert timeout == 180.0
        self.posts.append(json)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_native_video_prompt_matches_tanyapi_gpt55_file_contract() -> None:
    payload = {
        "prompt_ru": "Кинематографичный русский промпт",
        "prompt_en": "Cinematic English prompt",
        "negative_prompt": "flicker, jitter",
        "camera_movement_ru": "Плавный dolly-in",
        "timeline_ru": ["Общий план", "Приближение", "Крупный план"],
        "visual_style_ru": "Контровой свет",
        "audio_notes_ru": "Городской фон",
        "model_hint": "Seedance 2.0",
        "key_details": ["dolly-in", "контровой свет"],
    }
    response = _Response(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": __import__("json").dumps(payload)}],
                }
            ]
        }
    )
    client = _Client([response])

    result = await video_provider.build_video_prompt(
        client,  # type: ignore[arg-type]
        video_url="https://cdn.example/reference.mov",
        instruction="Сохрани движение камеры",
        duration_seconds=12,
        filename="reference.mov",
    )

    assert result.model == "gpt-5-5"
    assert result.payload["camera_movement_ru"] == "Плавный dolly-in"
    assert result.payload["timeline_ru"] == ["Общий план", "Приближение", "Крупный план"]
    body = client.posts[0]
    assert body["model"] == "gpt-5-5"
    assert body["reasoning"] == {"effort": "high"}
    user_content = body["input"][1]["content"]
    assert user_content[1] == {
        "type": "input_file",
        "file_url": "https://cdn.example/reference.mov",
        "filename": "reference.mov",
    }


@pytest.mark.asyncio
async def test_native_failure_falls_back_to_six_chronological_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = AsyncMock(side_effect=RuntimeError("native unavailable"))
    frames = AsyncMock(
        return_value=video_provider._result(
            {
                "prompt_ru": "RU",
                "prompt_en": "EN",
                "timeline_ru": ["1", "2", "3"],
            },
            model="gpt-5.5-frames",
        )
    )
    download = AsyncMock(return_value=b"video-bytes")
    extracted: list[tuple[bytes, float, int]] = []

    def extract(video_bytes: bytes, *, duration_seconds: float, max_frames: int) -> list[str]:
        extracted.append((video_bytes, duration_seconds, max_frames))
        return [f"data:image/jpeg;base64,frame{index}" for index in range(6)]

    monkeypatch.setattr(video_provider, "_analyze_native", native)
    monkeypatch.setattr(video_provider, "_analyze_frames", frames)
    monkeypatch.setattr(video_provider, "_download_video_bytes", download)
    monkeypatch.setattr(video_provider, "_extract_frame_data_urls_sync", extract)

    result = await video_provider.build_video_prompt(
        object(),  # type: ignore[arg-type]
        video_url="https://cdn.example/reference.mp4",
        duration_seconds=18,
    )

    assert result.model == "gpt-5.5-frames"
    assert extracted == [(b"video-bytes", 18.0, 6)]
    assert len(frames.await_args.kwargs["frame_data_urls"]) == 6


def test_video_preflight_reads_actual_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        video_prompt_media.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=b"42.125\n", stderr=b""),
    )

    duration = video_prompt_media.probe_video_duration_seconds(b"valid-video-bytes")

    assert duration == pytest.approx(42.125)


def test_video_preflight_enforces_sixty_second_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        video_prompt_media.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=b"60.01\n", stderr=b""),
    )

    with pytest.raises(PromptToolProviderError, match="60 секунд"):
        video_prompt_media.probe_video_duration_seconds(b"long-video-bytes")


@pytest.mark.asyncio
async def test_runtime_video_prompt_uses_probed_duration_and_reuses_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download = AsyncMock(return_value=b"source-video")
    build = AsyncMock(
        return_value=PromptToolProviderResult(
            model="gpt-5-5",
            payload={"prompt_ru": "RU", "prompt_en": "EN"},
            credits_consumed=None,
        )
    )
    monkeypatch.setattr(prompt_contract, "_download_video_bytes", download)
    monkeypatch.setattr(prompt_contract, "probe_video_duration_seconds", lambda _data: 47.5)
    monkeypatch.setattr(prompt_contract, "build_video_prompt", build)

    client = object.__new__(KiePromptToolsClient)
    client._client = object()  # type: ignore[assignment]

    result = await client.build_video_prompt(
        video_url="https://cdn.example/reference.mp4",
        instruction="Сохрани движение",
        duration_seconds=5,
    )

    assert result.model == "gpt-5-5"
    download.assert_awaited_once_with(client._client, "https://cdn.example/reference.mp4")
    assert build.await_args.kwargs["duration_seconds"] == pytest.approx(47.5)
    assert build.await_args.kwargs["video_bytes"] == b"source-video"
    assert build.await_args.kwargs["instruction"] == "Сохрани движение"


def test_installed_prompt_contract_exposes_tanyapi_models() -> None:
    assert prompt_module._TOOL_MODEL["image_analysis"] == "gpt-5-4"
    assert prompt_module._TOOL_MODEL["video_prompt"] == "gpt-5-5"
    assert KiePromptToolsClient.build_video_prompt.__module__ == "app.services.tanyapi_prompt_contract"


def test_tanyapi_video_limits_are_preserved() -> None:
    assert video_provider.VIDEO_PROMPT_FRAME_COUNT == 6
    assert video_provider.VIDEO_PROMPT_MAX_VIDEO_BYTES == 30 * 1024 * 1024
    assert video_provider.VIDEO_PROMPT_MAX_DURATION_SECONDS == 60
