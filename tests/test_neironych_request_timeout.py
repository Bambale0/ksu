from __future__ import annotations

import base64

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.providers.neironych_image import NeironychImageClient
from app.providers.neironych_video import NeironychVideoClient


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["image", "video"])
@pytest.mark.parametrize("seconds", [600, 420])
async def test_generation_post_uses_configured_timeout(monkeypatch, api, seconds):
    # Exercise the public adapter methods with a shorter injected client default.
    # A transport sees the actual timeout sent to HTTPX without waiting in real time.
    monkeypatch.setattr(settings, "neironych_request_timeout_seconds", seconds, raising=False)
    captured = []

    def respond(request):
        captured.append(request)
        if api == "image":
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"jpeg").decode()}]})
        return httpx.Response(202, json={"request_id": "video-test"})

    async with httpx.AsyncClient(
        base_url="https://provider.example",
        timeout=httpx.Timeout(60, connect=10),
        transport=httpx.MockTransport(respond),
    ) as http:
        if api == "image":
            client = NeironychImageClient("test-key", "https://provider.example", client=http)
            await client.create_nano_banana_pro(
                prompt="portrait", aspect_ratio="1:1", resolution="1K",
                image_urls=[], idempotency_key="timeout-regression",
            )
        else:
            client = NeironychVideoClient("test-key", "https://provider.example", client=http)
            await client.create_video(
                model="seedance-2.5",
                payload={"prompt": "Animate", "duration": 4, "resolution": "480p", "aspect_ratio": "9:16"},
                idempotency_key="timeout-regression",
            )
    assert len(captured) == 1
    assert captured[0].extensions["timeout"]["read"] == seconds
    assert captured[0].extensions["timeout"]["connect"] == 10
    assert captured[0].headers["Idempotency-Key"] == "timeout-regression"


@pytest.mark.asyncio
async def test_video_status_keeps_short_timeout():
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"status": "processing"})

    async with httpx.AsyncClient(
        base_url="https://provider.example", timeout=httpx.Timeout(60, connect=10),
        transport=httpx.MockTransport(respond),
    ) as http:
        client = NeironychVideoClient("test-key", "https://provider.example", client=http)
        await client.get_video("video-test")
    assert captured[0].extensions["timeout"]["read"] == 60


def test_timeout_default_is_600_seconds(monkeypatch):
    monkeypatch.delenv("NEIRONYCH_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert Settings(_env_file=None).neironych_request_timeout_seconds == 600


@pytest.mark.parametrize("seconds", [0, -1, 3601])
def test_timeout_rejects_invalid_values(seconds):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, neironych_request_timeout_seconds=seconds)
