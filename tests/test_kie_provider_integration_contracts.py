from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.providers.kie import KieClient
from app.providers.kie_veo import KieVeoClient
from app.services.kie_image_contracts import IMAGE_MODELS
from app.services.kie_video_contracts import KieVideoContractError, VIDEO_MODELS

IMG = "https://cdn.example.com/source.png"
IMG_2 = "https://cdn.example.com/second.png"
IMG_3 = "https://cdn.example.com/third.png"
MP4 = "https://cdn.example.com/motion.mp4"
AUDIO = "https://cdn.example.com/audio.mp3"
TOKEN = "test-token"

VALID_MARKET_MODEL_INPUTS: dict[str, dict[str, Any]] = {
    "google/nano-banana": {
        "prompt": "poster",
        "aspect_ratio": "1:1",
        "output_format": "png",
    },
    "google/nano-banana-edit": {
        "prompt": "edit poster",
        "aspect_ratio": "1:1",
        "output_format": "png",
        "image_urls": [IMG],
    },
    "nano-banana-pro": {
        "prompt": "premium poster",
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "output_format": "png",
        "image_input": [IMG],
    },
    "nano-banana-2": {
        "prompt": "v2 poster",
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "output_format": "jpg",
        "image_input": [IMG],
    },
    "nano-banana-2-lite": {
        "prompt": "lite poster",
        "aspect_ratio": "1:1",
        "image_urls": [IMG],
    },
    "bytedance/seedream": {
        "prompt": "seedream poster",
        "image_size": "square_hd",
    },
    "bytedance/seedream-v4-text-to-image": {
        "prompt": "seedream v4 set",
        "image_size": "square_hd",
        "image_resolution": "1K",
        "max_images": 2,
    },
    "bytedance/seedream-v4-edit": {
        "prompt": "seedream v4 edit",
        "image_size": "square_hd",
        "image_resolution": "1K",
        "max_images": 2,
        "image_urls": [IMG],
    },
    "seedream/4.5-text-to-image": {
        "prompt": "seedream 4.5 poster",
        "aspect_ratio": "1:1",
        "quality": "basic",
    },
    "seedream/4.5-edit": {
        "prompt": "seedream 4.5 edit",
        "aspect_ratio": "1:1",
        "quality": "basic",
        "image_urls": [IMG],
    },
    "seedream/5-lite-text-to-image": {
        "prompt": "seedream 5 lite poster",
        "aspect_ratio": "1:1",
        "quality": "basic",
        "output_format": "png",
    },
    "seedream/5-lite-image-to-image": {
        "prompt": "seedream 5 lite edit",
        "aspect_ratio": "1:1",
        "quality": "basic",
        "output_format": "png",
        "image_urls": [IMG],
    },
    "seedream/5-pro-text-to-image": {
        "prompt": "seedream 5 pro poster",
        "aspect_ratio": "1:1",
        "quality": "basic",
        "output_format": "png",
    },
    "seedream/5-pro-image-to-image": {
        "prompt": "seedream 5 pro edit",
        "aspect_ratio": "1:1",
        "quality": "basic",
        "output_format": "png",
        "image_urls": [IMG],
    },
    "seedream/5-pro-layer-decomposition": {
        "prompt": "split layers",
        "output_format": "png",
    },
    "gpt-image/1.5-text-to-image": {
        "prompt": "gpt image 1.5 poster",
        "aspect_ratio": "1:1",
        "quality": "medium",
    },
    "gpt-image/1.5-image-to-image": {
        "prompt": "gpt image 1.5 edit",
        "aspect_ratio": "1:1",
        "quality": "medium",
        "input_urls": [IMG],
    },
    "gpt-image-2-text-to-image": {
        "prompt": "gpt image 2 poster",
        "aspect_ratio": "1:1",
        "resolution": "1K",
    },
    "gpt-image-2-image-to-image": {
        "prompt": "gpt image 2 edit",
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "input_urls": [IMG],
    },
    "wan/2-7-image": {
        "prompt": "wan image",
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "n": 1,
        "thinking_mode": False,
        "watermark": False,
        "nsfw_checker": True,
    },
    "wan/2-7-image-pro": {
        "prompt": "wan image pro",
        "aspect_ratio": "1:1",
        "resolution": "1K",
        "n": 1,
        "thinking_mode": False,
        "watermark": False,
        "nsfw_checker": True,
    },
    "grok-imagine/text-to-image": {
        "prompt": "grok image",
        "aspect_ratio": "1:1",
        "enable_pro": False,
        "nsfw_checker": True,
    },
    "grok-imagine/image-to-image": {
        "prompt": "grok edit",
        "image_urls": [IMG],
        "nsfw_checker": True,
    },
    "wan/2-7-text-to-video": {
        "prompt": "wan video",
        "aspect_ratio": "16:9",
        "prompt_extend": False,
        "watermark": False,
    },
    "wan/2-7-image-to-video": {
        "prompt": "wan first frame",
        "first_frame_url": IMG,
        "prompt_extend": False,
        "watermark": False,
    },
    "wan/2-7-videoedit": {
        "prompt": "wan edit",
        "audio_setting": {"mode": "auto"},
        "duration": 4,
        "prompt_extend": False,
        "watermark": False,
    },
    "wan/2-7-r2v": {
        "prompt": "wan references",
        "reference_image": IMG,
        "reference_video": MP4,
        "prompt_extend": False,
        "watermark": False,
    },
    "bytedance/seedance-1.5-pro": {
        "prompt": "seedance 1.5",
        "fixed_lens": False,
        "generate_audio": False,
        "nsfw_checker": True,
        "duration": 5,
        "input_urls": [IMG],
    },
    "bytedance/seedance-2": {
        "prompt": "seedance 2",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "duration": 8,
        "generate_audio": False,
        "nsfw_checker": True,
        "web_search": False,
        "reference_image_urls": [IMG],
    },
    "bytedance/seedance-2-fast": {
        "prompt": "seedance 2 fast",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "duration": 8,
        "generate_audio": False,
        "nsfw_checker": True,
        "web_search": False,
        "reference_video_urls": [MP4],
    },
    "bytedance/seedance-2-mini": {
        "prompt": "seedance 2 mini",
        "aspect_ratio": "adaptive",
        "resolution": "720p",
        "duration": 8,
        "generate_audio": False,
        "nsfw_checker": True,
        "web_search": False,
        "reference_audio_urls": [AUDIO],
    },
    "bytedance/seedance-2-5": {
        "prompt": "seedance 2.5",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration": 8,
        "output_format": "mp4",
        "generate_audio": False,
        "nsfw_checker": True,
        "return_last_frame": False,
        "web_search": False,
        "reference_image_urls": [IMG, IMG_2],
    },
    "kling-3.0/video": {
        "prompt": "kling 3",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration": 5,
        "sound": False,
        "multi_shots": False,
        "image_urls": [IMG],
        "kling_elements": [
            {
                "name": "hero",
                "element_input_urls": [IMG, IMG_2],
                "element_input_audio_urls": [],
            }
        ],
    },
    "kling-2.6/motion-control": {
        "input_urls": [IMG],
        "video_urls": [MP4],
        "mode": "720p",
        "character_orientation": "image",
    },
    "kling-3.0/motion-control": {
        "input_urls": [IMG],
        "video_urls": [MP4],
        "mode": "1080p",
        "character_orientation": "image",
        "background_source": "input_video",
    },
    "gemini-omni-video": {
        "prompt": "gemini omni",
        "image_urls": [IMG],
        "video_list": [{"url": MP4, "start": 0, "ends": 1}],
        "character_ids": ["character-1"],
        "audio_ids": ["audio-1"],
    },
    "grok-imagine/text-to-video": {
        "prompt": "grok video",
        "duration": 5,
    },
    "grok-imagine/image-to-video": {
        "prompt": "grok i2v",
        "duration": 5,
        "image_urls": [IMG],
    },
    "grok-imagine-video-1-5-preview": {
        "prompt": "grok preview video",
        "duration": 5,
    },
    "grok-imagine/upscale": {"task_id": "task_123"},
    "grok-imagine/extend": {
        "task_id": "task_123",
        "extend_at": 3,
        "extend_times": 1,
    },
}


def _task_response(task_id: str = "task_kie") -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": 200, "msg": "success", "data": {"taskId": task_id}},
    )


def test_kie_market_model_smoke_fixtures_cover_every_known_contract() -> None:
    assert set(VALID_MARKET_MODEL_INPUTS) == IMAGE_MODELS | VIDEO_MODELS


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(VALID_MARKET_MODEL_INPUTS))
async def test_kie_client_posts_every_known_market_model_contract(model: str) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _task_response()

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model=model,
            input_data=VALID_MARKET_MODEL_INPUTS[model],
        )
    finally:
        await client.aclose()

    assert task_id == "task_kie"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/jobs/createTask"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(request.content)
    assert body["model"] == model
    assert isinstance(body["input"], dict)


@pytest.mark.asyncio
async def test_kie_client_posts_seedream_unified_create_task_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _task_response("task_seedream")

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
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
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
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
        return _task_response("task_seedance")

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
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
                "reference_video_urls ": [MP4],
            },
        )
    finally:
        await client.aclose()

    assert task_id == "task_seedance"
    body = json.loads(requests[0].content)
    assert body["model"] == "bytedance/seedance-2"
    assert body["input"]["aspect_ratio"] == "16:9"
    assert body["input"]["duration"] == 8
    assert body["input"]["reference_video_urls"] == [MP4]
    assert "reference_video_urls " not in body["input"]
    assert "fixed_lens" not in body["input"]
    assert "return_last_frame" not in body["input"]


@pytest.mark.asyncio
async def test_kie_client_rejects_seedance_25_mixed_frame_and_reference_modes_before_http() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _task_response("unexpected")

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
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
                    "first_frame_url": IMG,
                    "reference_image_urls": [IMG_2],
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
        return _task_response("task_wan")

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model="wan/2-7-image-to-video",
            input_data={
                "prompt": "camera push in",
                "first_frame_url": IMG,
                "last_frame_url": IMG_2,
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
    assert body["input"]["first_frame_url"] == IMG
    assert body["input"]["last_frame_url"] == IMG_2
    assert body["input"]["prompt_extend"] is True
    assert body["input"]["watermark"] is False


@pytest.mark.asyncio
async def test_kie_client_rejects_kling_motion_without_required_pair_before_http() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _task_response("unexpected")

    client = KieClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(
            KieVideoContractError,
            match="exactly one reference image and one motion video",
        ):
            await client.create_task(
                model="kling-3.0/motion-control",
                input_data={
                    "input_urls": [IMG],
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
        return _task_response("task_veo")

    client = KieVeoClient(TOKEN)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.ai",
        headers={"Authorization": f"Bearer {TOKEN}"},
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            input_data={
                "prompt": "material-driven video",
                "veo_model": "veo3_fast",
                "aspect_ratio": "9:16",
                "generation_type": "REFERENCE_2_VIDEO",
                "image_urls": [IMG_3],
                "enable_fallback": True,
                "enable_translation": False,
            },
            callback_url="https://example.com/veo/callback",
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
    assert body["aspect_ratio"] == "9:16"
    assert body["generationType"] == "REFERENCE_2_VIDEO"
    assert body["imageUrls"] == [IMG_3]
    assert body["callBackUrl"] == "https://example.com/veo/callback"
    assert body["enableFallback"] is True
    assert body["enableTranslation"] is False
    assert body["resolution"] == "720p"
    assert body["duration"] == 4
