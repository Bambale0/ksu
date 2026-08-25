from __future__ import annotations

import json

import httpx
import pytest

from app.providers.kie import KieClient
from app.providers.kie_veo import KieVeoClient
from app.services.kie_video_contracts import KieVideoContractError


@pytest.mark.asyncio
async def test_kie_client_posts_seedream_unified_create_task_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_seedream"}})

    client = KieClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model="bytedance/seedream",
            input_data={
                "prompt": "poster",
                "image_size": "square_hd",
                "guidance_scale": 2.5,
                "seed": 0,
            },
            callback_url="https://example.com/kie/callback",
        )
    finally:
        await client.aclose()

    assert task_id == "task_seedream"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/jobs/createTask"
    assert request.headers["authorization"] == "Bearer test-token"
    body = json.loads(request.content)
    assert body == {
        "model": "bytedance/seedream",
        "callBackUrl": "https://example.com/kie/callback",
        "input": {
            "prompt": "poster",
            "image_size": "square_hd",
            "guidance_scale": 2.5,
            "seed": 0,
        },
    }


@pytest.mark.asyncio
async def test_kie_client_normalizes_seedance_2_payload_before_http() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_seedance"}})

    client = KieClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model="bytedance/seedance-2",
            input_data={
                "prompt": "cinematic product shot",
                "aspect_ratio": "adaptive",
                "resolution": "720p",
                "duration": "8",
                "fixed_lens": True,
                "return_last_frame": False,
                "generate_audio": True,
                "reference_video_urls ": ["https://cdn.example.com/ref.mp4"],
            },
        )
    finally:
        await client.aclose()

    assert task_id == "task_seedance"
    body = json.loads(requests[0].content)
    assert body["model"] == "bytedance/seedance-2"
    assert body["input"]["aspect_ratio"] == "16:9"
    assert body["input"]["duration"] == 8
    assert body["input"]["reference_video_urls"] == ["https://cdn.example.com/ref.mp4"]
    assert "reference_video_urls " not in body["input"]
    assert "fixed_lens" not in body["input"]
    assert "return_last_frame" not in body["input"]


@pytest.mark.asyncio
async def test_kie_client_rejects_seedance_25_mixed_frame_and_reference_modes_before_http() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "unexpected"}})

    client = KieClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KieVideoContractError, match="mutually exclusive"):
            await client.create_task(
                model="bytedance/seedance-2-5",
                input_data={
                    "prompt": "transition",
                    "aspect_ratio": "16:9",
                    "resolution": "1080p",
                    "duration": 8,
                    "first_frame_url": "https://cdn.example.com/first.png",
                    "reference_image_urls": ["https://cdn.example.com/ref.png"],
                },
            )
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.asyncio
async def test_kie_client_posts_wan_27_image_to_video_first_last_frames() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_wan"}})

    client = KieClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model="wan/2-7-image-to-video",
            input_data={
                "prompt": "camera push in",
                "first_frame_url": "https://cdn.example.com/first.png",
                "last_frame_url": "https://cdn.example.com/last.png",
                "prompt_extend": True,
                "watermark": False,
                "seed": 123456,
            },
        )
    finally:
        await client.aclose()

    assert task_id == "task_wan"
    body = json.loads(requests[0].content)
    assert body["model"] == "wan/2-7-image-to-video"
    assert body["input"]["first_frame_url"] == "https://cdn.example.com/first.png"
    assert body["input"]["last_frame_url"] == "https://cdn.example.com/last.png"
    assert body["input"]["prompt_extend"] is True
    assert body["input"]["watermark"] is False


@pytest.mark.asyncio
async def test_kie_client_rejects_kling_motion_without_required_pair_before_http() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "unexpected"}})

    client = KieClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KieVideoContractError, match="exactly one reference image and one motion video"):
            await client.create_task(
                model="kling-3.0/motion-control",
                input_data={
                    "input_urls": ["https://cdn.example.com/character.png"],
                    "mode": "1080p",
                },
            )
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.asyncio
async def test_kie_veo_client_posts_generate_contract_with_reference_mode() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task_veo"}})

    client = KieVeoClient("test-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": "Bearer test-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.generate(
            prompt="material-driven video",
            model="veo3_fast",
            aspect_ratio="9:16",
            generation_type="REFERENCE_2_VIDEO",
            image_urls=["https://cdn.example.com/material.png"],
            callback_url="https://example.com/veo/callback",
            enable_fallback=True,
            enable_translation=False,
        )
    finally:
        await client.aclose()

    assert task_id == "task_veo"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/veo/generate"
    body = json.loads(request.content)
    assert body["prompt"] == "material-driven video"
    assert body["model"] == "veo3_fast"
    assert body["aspectRatio"] == "9:16"
    assert body["generationType"] == "REFERENCE_2_VIDEO"
    assert body["imageUrls"] == ["https://cdn.example.com/material.png"]
    assert body["callBackUrl"] == "https://example.com/veo/callback"
    assert body["enableFallback"] is True
    assert body["enableTranslation"] is False
