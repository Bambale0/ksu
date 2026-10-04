from __future__ import annotations

import json

import httpx
import pytest

from app.providers.nexus_pinterest_quality import NexusPinterestQualityClient


@pytest.mark.asyncio
async def test_nexus_pinterest_quality_accepts_scene_two_identities_and_candidate() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        observed.update(body)
        payload = {
            "scene_match_score": 90,
            "identity_match_score": 91,
            "pose_match_score": 88,
            "composition_match_score": 87,
            "anatomy_ok": True,
            "issues": [],
            "retry_instruction": "",
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPinterestQualityClient("test-key", client=http_client)
        result = await client.evaluate(
            scene_url="https://cdn.example.test/scene.jpg",
            identity_urls=[
                "https://cdn.example.test/id1.jpg",
                "https://cdn.example.test/id2.jpg",
            ],
            candidate_url="https://cdn.example.test/candidate.jpg",
        )

    assert result.model == "gpt-6-sol"
    assert result.payload["identity_match_score"] == 91
    content = observed["messages"][1]["content"]
    image_blocks = [item for item in content if item.get("type") == "image_url"]
    assert len(image_blocks) == 4


@pytest.mark.asyncio
async def test_nexus_pinterest_quality_rejects_more_than_two_identity_images() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPinterestQualityClient("test-key", client=http_client)
        with pytest.raises(Exception, match="at most 2 identity"):
            await client.evaluate(
                scene_url="https://cdn.example.test/scene.jpg",
                identity_urls=[
                    "https://cdn.example.test/id1.jpg",
                    "https://cdn.example.test/id2.jpg",
                    "https://cdn.example.test/id3.jpg",
                ],
                candidate_url="https://cdn.example.test/candidate.jpg",
            )


def test_quality_provider_selection_uses_nexus_until_vision_limit() -> None:
    from app.services.pinterest_quality_gate import PinterestRepeatQualityGate

    assert PinterestRepeatQualityGate._quality_provider_key(["id1"]) == "nexus-pinterest-repeat-quality"
    assert (
        PinterestRepeatQualityGate._quality_provider_key(["id1", "id2"])
        == "nexus-pinterest-repeat-quality"
    )
    assert (
        PinterestRepeatQualityGate._quality_provider_key(["id1", "id2", "id3"])
        == "kie-pinterest-repeat-quality"
    )
