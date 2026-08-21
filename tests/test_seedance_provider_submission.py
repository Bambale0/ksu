from __future__ import annotations

from typing import Any

import pytest

from app.providers.kie import KieClient


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
