from __future__ import annotations

import json

import httpx
import pytest

from app.providers.nexus_pinterest_analysis import NexusPinterestAnalysisClient


@pytest.mark.asyncio
async def test_nexus_pinterest_scene_analysis_uses_gpt6_sol_vision() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        observed.update(body)
        content = {
            "scene": "studio portrait",
            "composition": "subject centered",
            "camera": "eye level",
            "pose": "standing",
            "lighting": "soft side light",
            "environment": "plain backdrop",
            "wardrobe": "black jacket",
            "expression": "calm",
            "gaze": "to camera",
            "must_preserve": ["centered crop", "soft side light"],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPinterestAnalysisClient("test-key", client=http_client)
        result = await client.analyze(image_url="https://cdn.example.test/scene.jpg")

    assert result.model == "gpt-6-sol"
    assert result.payload["pose"] == "standing"
    assert observed["model"] == "gpt-6-sol"
    user_content = observed["messages"][1]["content"]
    assert user_content[-1] == {
        "type": "image_url",
        "image_url": {"url": "https://cdn.example.test/scene.jpg"},
    }
