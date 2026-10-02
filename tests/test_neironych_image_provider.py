from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.providers.neironych_image import NeironychImageClient


@pytest.mark.asyncio
async def test_neironych_nano_pro_text_generation_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Idempotency-Key"] == "generation:test:provider:0"
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(b"jpeg-bytes").decode()}]},
        )

    async with httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = NeironychImageClient("test-key", "https://api.example", client=http_client)
        result = await client.create_nano_banana_pro(
            prompt="portrait",
            aspect_ratio="3:4",
            resolution="2K",
            image_urls=[],
            idempotency_key="generation:test:provider:0",
        )

    assert result.content == b"jpeg-bytes"
    assert captured == {
        "model": "nano-banana-pro",
        "prompt": "portrait",
        "n": 1,
        "resolution": "2k",
        "aspect_ratio": "3:4",
        "response_format": "b64_json",
    }


@pytest.mark.asyncio
async def test_neironych_nano_pro_edit_contract_uses_images() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/edits"
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(b"edited-jpeg").decode()}]},
        )

    async with httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = NeironychImageClient("test-key", "https://api.example", client=http_client)
        result = await client.create_nano_banana_pro(
            prompt="preserve identity",
            aspect_ratio="1:1",
            resolution="4K",
            image_urls=[
                "https://example.test/a.jpg",
                "https://example.test/a.jpg",
                "https://example.test/b.jpg",
            ],
            idempotency_key="generation:test:provider:0",
        )

    assert result.content == b"edited-jpeg"
    assert captured["resolution"] == "4k"
    assert captured["images"] == [
        {"image_url": "https://example.test/a.jpg"},
        {"image_url": "https://example.test/b.jpg"},
    ]


@pytest.mark.asyncio
async def test_neironych_image_error_redacts_signed_reference_url() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "message": (
                        "bad ref https://storage.example/ref.jpg?"
                        "X-Amz-Credential=0123456789abcdef0123456789abcdef&"
                        "X-Amz-Signature=abcdefabcdefabcdefabcdefabcdefabcdef"
                    )
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://api.example",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = NeironychImageClient("test-key", "https://api.example", client=http_client)
        with pytest.raises(Exception) as caught:
            await client.create_nano_banana_pro(
                prompt="portrait",
                aspect_ratio="1:1",
                resolution="1K",
                image_urls=[],
                idempotency_key="generation:test:provider:0",
            )

    message = str(caught.value)
    assert "X-Amz-Credential" not in message
    assert "X-Amz-Signature" not in message
    assert "https://storage.example/ref.jpg?[REDACTED]" in message
