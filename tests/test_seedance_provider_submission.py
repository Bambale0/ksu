from __future__ import annotations

from typing import Any

import pytest

from app.providers.kie import KieClient
from app.services.kie_video_contracts import KieVideoContractError


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"data": {"taskId": "seedance-task-1"}}


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, path: str, *, json: dict[str, Any]) -> _Response:
        self.calls.append((path, json))
        return _Response()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_seedance_20_default_like_payload_reaches_kie() -> None:
    """Regression: old ROXY defaults used fields Kie's current 2.0 schema rejects."""

    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    task_id = await client.create_task(
        model="bytedance/seedance-2",
        input_data={
            "prompt": "cinematic portrait",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
            "generate_audio": False,
            "return_last_frame": False,
            "web_search": False,
        },
        callback_url="https://example.test/webhooks/kie?generation_id=20",
    )

    assert task_id == "seedance-task-1"
    assert len(fake.calls) == 1
    path, body = fake.calls[0]
    assert path == "/api/v1/jobs/createTask"
    assert body["model"] == "bytedance/seedance-2"
    assert body["input"]["aspect_ratio"] == "16:9"
    assert "return_last_frame" not in body["input"]
    assert "fixed_lens" not in body["input"]


@pytest.mark.asyncio
async def test_seedance_20_hybrid_frame_and_references_is_rejected_before_kie() -> None:
    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    with pytest.raises(KieVideoContractError, match="mutually exclusive"):
        await client.create_task(
            model="bytedance/seedance-2",
            input_data={
                "prompt": "keep the hero and follow the motion reference",
                "first_frame_url": "https://cdn.example/first.png",
                "last_frame_url": "https://cdn.example/last.png",
                "reference_image_urls": ["https://cdn.example/hero.png"],
                "reference_video_urls": ["https://cdn.example/motion.mp4"],
                "reference_audio_urls": ["https://cdn.example/voice.wav"],
                "duration": 10,
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "generate_audio": True,
                "web_search": False,
            },
            callback_url="https://example.test/webhooks/kie?generation_id=21",
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_seedance_20_reference_mode_reaches_kie() -> None:
    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    task_id = await client.create_task(
        model="bytedance/seedance-2",
        input_data={
            "prompt": "keep the subject consistent",
            "reference_image_urls": ["https://cdn.example/hero.png"],
            "reference_video_urls": ["https://cdn.example/motion.mp4"],
            "reference_audio_urls": ["https://cdn.example/voice.wav"],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "generate_audio": True,
            "web_search": False,
        },
        callback_url="https://example.test/webhooks/kie?generation_id=22",
    )

    assert task_id == "seedance-task-1"
    assert len(fake.calls) == 1
    _, body = fake.calls[0]
    provider_input = body["input"]
    assert provider_input["reference_image_urls"] == ["https://cdn.example/hero.png"]
    assert provider_input["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert provider_input["reference_audio_urls"] == ["https://cdn.example/voice.wav"]
    assert "first_frame_url" not in provider_input
    assert "last_frame_url" not in provider_input


@pytest.mark.asyncio
async def test_seedance_20_legacy_trailing_space_reference_key_is_normalized() -> None:
    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    await client.create_task(
        model="bytedance/seedance-2-fast",
        input_data={
            "prompt": "follow reference motion",
            "reference_video_urls ": ["https://cdn.example/motion.mp4"],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )

    assert len(fake.calls) == 1
    _, body = fake.calls[0]
    assert body["input"]["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "reference_video_urls " not in body["input"]


@pytest.mark.asyncio
async def test_seedance_20_mini_keeps_documented_adaptive_ratio() -> None:
    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    await client.create_task(
        model="bytedance/seedance-2-mini",
        input_data={
            "prompt": "portrait motion",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    assert fake.calls[0][1]["input"]["aspect_ratio"] == "adaptive"


@pytest.mark.asyncio
async def test_seedance_25_create_task_reaches_kie_with_normalized_payload() -> None:
    client = KieClient("test-key")
    fake = _FakeAsyncClient()
    client._client = fake  # type: ignore[attr-defined]

    task_id = await client.create_task(
        model="bytedance/seedance-2-5",
        input_data={
            "prompt": "пикачу бежит по пляжу",
            "duration": "5",
            "resolution": "720p",
            "aspect_ratio": "adaptive",
            "output_format": "mp4",
            "generate_audio": False,
            "return_last_frame": False,
            "web_search": False,
            "nsfw_checker": True,
        },
        callback_url="https://example.test/webhooks/kie?generation_id=1",
    )

    assert task_id == "seedance-task-1"
    assert fake.calls == [
        (
            "/api/v1/jobs/createTask",
            {
                "model": "bytedance/seedance-2-5",
                "input": {
                    "prompt": "пикачу бежит по пляжу",
                    "duration": 5,
                    "resolution": "720p",
                    "aspect_ratio": "adaptive",
                    "output_format": "mp4",
                    "generate_audio": False,
                    "return_last_frame": False,
                    "web_search": False,
                    "nsfw_checker": True,
                },
                "callBackUrl": "https://example.test/webhooks/kie?generation_id=1",
            },
        )
    ]