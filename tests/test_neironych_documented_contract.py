"""Regression cases transcribed from the Neironych guide, not live paid requests."""

from __future__ import annotations

import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.providers.neironych_image import NeironychImageClient
from app.providers.neironych_video import NeironychProviderError, NeironychVideoClient
from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)

PHOTO = "https://media.example/photo.jpg"
VIDEO = "https://media.example/source.mp4"


def video_body(**changes):
    return {
        "prompt": "Animate @Image 1",
        "reference_images": [{"url": PHOTO}],
        "duration": 4,
        "resolution": "480p",
        "aspect_ratio": "9:16",
        **changes,
    }


@pytest.mark.parametrize("include_duration", [True, False])
def test_documented_edit_is_accepted(include_duration):
    payload = {
        "prompt": "Replace sky in @Video 1",
        "reference_videos": [{"url": VIDEO}],
        "omni_reference_task_type": "edit",
        "aspect_ratio": "adaptive",
        "resolution": "720p",
    }
    if include_duration:
        payload["duration"] = -1
    before = copy.deepcopy(payload)
    assert normalize_neironych_video_input("seedance-2.5", payload) == before
    assert payload == before


@pytest.mark.parametrize(
    "changes", [{"duration": 5}, {"aspect_ratio": "9:16"}, {"size": "720x1280"}]
)
def test_edit_rejects_fixed_output_geometry(changes):
    payload = {
        "prompt": "Replace sky in @Video 1",
        "reference_videos": [{"url": VIDEO}],
        "omni_reference_task_type": "edit",
        **changes,
    }
    with pytest.raises(NeironychVideoContractError):
        normalize_neironych_video_input("seedance-2.5", payload)


def test_only_seedance_20_frames_allow_fixed_ratio():
    payload = video_body(prompt="Animate frame", start_image={"url": PHOTO})
    payload.pop("reference_images")
    with pytest.raises(NeironychVideoContractError):
        normalize_neironych_video_input("seedance-2.5", payload)
    assert normalize_neironych_video_input("seedance-2.0", payload)["aspect_ratio"] == "9:16"


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": 123},
        {"watermark": True},
        {"n": 2},
        {"n": True},
        {"duration": 4.7},
        {"duration": True},
        {"reference_images": [{"url": "https://user:pass@media.example/ref.jpg"}]},
    ],
)
def test_illegal_seedance_parameters_are_rejected(changes):
    with pytest.raises(NeironychVideoContractError):
        normalize_neironych_video_input("seedance-2.5", video_body(**changes))


@pytest.mark.parametrize("ratio", ["auto", "100:1"])
@pytest.mark.asyncio
async def test_nano_invalid_ratio_never_sends_http(ratio):
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": "eA=="}]})

    async with httpx.AsyncClient(
        base_url="https://provider.example", transport=httpx.MockTransport(respond)
    ) as http:
        client = NeironychImageClient("test-key", "https://provider.example", client=http)
        with pytest.raises(NeironychProviderError):
            await client.create_nano_banana_pro(
                prompt="portrait",
                aspect_ratio=ratio,
                resolution="1K",
                image_urls=[],
                idempotency_key="regression-request-key",
            )
    assert calls == []


@pytest.mark.asyncio
async def test_nano_retains_success_request_id():
    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            headers={"X-Request-Id": "provider-image-1"},
            json={"data": [{"b64_json": base64.b64encode(b"jpeg").decode()}]},
        )

    async with httpx.AsyncClient(
        base_url="https://provider.example", transport=httpx.MockTransport(respond)
    ) as http:
        client = NeironychImageClient("test-key", "https://provider.example", client=http)
        result = await client.create_nano_banana_pro(
            prompt="portrait",
            aspect_ratio="1:1",
            resolution="1K",
            image_urls=[],
            idempotency_key="regression-request-key",
        )
    assert result.request_id == "provider-image-1"


@pytest.mark.parametrize("api", ["image", "video"])
@pytest.mark.parametrize(
    "error_body",
    [
        {"detail": "provider_rate_limited"},
        {"error": {"type": "provider_rate_limited", "message": "Slow down"}},
    ],
)
@pytest.mark.asyncio
async def test_transport_retains_error_metadata(api, error_body):
    def respond(_request):
        return httpx.Response(
            429, headers={"X-Request-Id": "provider-error-1", "Retry-After": "45"}, json=error_body
        )

    async with httpx.AsyncClient(
        base_url="https://provider.example", transport=httpx.MockTransport(respond)
    ) as http:
        with pytest.raises(NeironychProviderError) as caught:
            if api == "image":
                client = NeironychImageClient("test-key", "https://provider.example", client=http)
                await client.create_nano_banana_pro(
                    prompt="x",
                    aspect_ratio="1:1",
                    resolution="1K",
                    image_urls=[],
                    idempotency_key="regression-key",
                )
            else:
                client = NeironychVideoClient("test-key", "https://provider.example", client=http)
                await client.create_video(
                    model="seedance-2.5", payload=video_body(), idempotency_key="regression-key"
                )
    assert caught.value.request_id == "provider-error-1"
    assert caught.value.error_code == "provider_rate_limited"
    assert caught.value.retry_after == 45


@pytest.mark.asyncio
async def test_retry_after_http_date_is_preserved():
    retry_date = format_datetime(datetime.now(UTC) + timedelta(seconds=70), usegmt=True)
    async with httpx.AsyncClient(
        base_url="https://provider.example",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                429, headers={"Retry-After": retry_date}, json={"detail": "provider_rate_limited"}
            )
        ),
    ) as http:
        with pytest.raises(NeironychProviderError) as caught:
            await NeironychVideoClient(
                "test-key", "https://provider.example", client=http
            ).get_video("task")
    assert 65 <= caught.value.retry_after <= 70


@pytest.mark.asyncio
async def test_paid_image_post_is_never_automatically_retried():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"type": "submission_outcome_unknown"}})

    async with httpx.AsyncClient(
        base_url="https://provider.example", transport=httpx.MockTransport(respond)
    ) as http:
        with pytest.raises(NeironychProviderError):
            await NeironychImageClient(
                "test-key", "https://provider.example", client=http
            ).create_nano_banana_pro(
                prompt="x",
                aspect_ratio="1:1",
                resolution="1K",
                image_urls=[],
                idempotency_key="regression-key",
            )
    assert len(calls) == 1
    assert json.loads(calls[0].content)["response_format"] == "b64_json"
