from __future__ import annotations

from typing import Any

import pytest

from app.providers.kie_veo import KieVeoClient


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"code": 200, "data": {"taskId": "veo-task-123"}}


class _Client:
    instances: list["_Client"] = []

    def __init__(self, **_kwargs: Any) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.__class__.instances.append(self)

    async def post(self, path: str, *, json: dict[str, Any]) -> _Response:
        self.posts.append((path, json))
        return _Response()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_veo_create_task_sends_selected_resolution_and_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Client.instances.clear()
    monkeypatch.setattr("app.providers.kie_veo.httpx.AsyncClient", _Client)

    client = KieVeoClient("test-key")
    task_id = await client.create_task(
        input_data={
            "prompt": "cinematic tracking shot",
            "veo_model": "veo3_fast",
            "aspect_ratio": "auto",
            "generation_type": "TEXT_2_VIDEO",
            "resolution": "1080p",
            "duration": 6,
        }
    )

    assert task_id == "veo-task-123"
    assert len(_Client.instances) == 1
    path, body = _Client.instances[0].posts[0]
    assert path == "/api/v1/veo/generate"
    assert body["resolution"] == "1080p"
    assert body["duration"] == 6
    assert body["model"] == "veo3_fast"
    assert body["generationType"] == "TEXT_2_VIDEO"
