from __future__ import annotations

import io
import json

import httpx
import pytest

from app.providers.kie import KieProviderError
from app.providers.kie_uploads import KieUploadClient


@pytest.mark.asyncio
async def test_kie_upload_accepts_download_url_and_preserves_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/file-stream-upload"
        body = await request.aread()
        assert b"hello-reference" in body
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "downloadUrl": "https://cdn.example/reference.png",
                    "fileName": "reference.png",
                    "mimeType": "image/png",
                    "fileSize": "15",
                },
            },
        )

    client = KieUploadClient(
        "test-key",
        "https://upload.example",
        transport=httpx.MockTransport(handler),
    )
    try:
        uploaded = await client.upload_stream(
            file_name="reference.png",
            content_type="image/png",
            stream=io.BytesIO(b"hello-reference"),
        )
    finally:
        await client.aclose()

    assert uploaded.url == "https://cdn.example/reference.png"
    assert uploaded.name == "reference.png"
    assert uploaded.mime_type == "image/png"
    assert uploaded.size == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("first_status", [429, 503])
async def test_kie_upload_retries_transient_http_and_rewinds_stream(
    monkeypatch: pytest.MonkeyPatch,
    first_status: int,
) -> None:
    bodies: list[bytes] = []

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.providers.kie_uploads.asyncio.sleep", no_sleep)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(first_status, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"fileUrl": "https://cdn.example/retry.png"},
            },
        )

    client = KieUploadClient(
        "test-key",
        "https://upload.example",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )
    try:
        uploaded = await client.upload_stream(
            file_name="retry.png",
            content_type="image/png",
            stream=io.BytesIO(b"same-reference-on-every-attempt"),
        )
    finally:
        await client.aclose()

    assert uploaded.url == "https://cdn.example/retry.png"
    assert len(bodies) == 2
    assert b"same-reference-on-every-attempt" in bodies[0]
    assert b"same-reference-on-every-attempt" in bodies[1]


@pytest.mark.asyncio
async def test_kie_upload_does_not_retry_permanent_provider_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def no_sleep(_seconds: float) -> None:
        raise AssertionError("permanent provider errors must not be retried")

    monkeypatch.setattr("app.providers.kie_uploads.asyncio.sleep", no_sleep)

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, text="invalid media")

    client = KieUploadClient(
        "test-key",
        "https://upload.example",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KieProviderError, match="HTTP 400"):
            await client.upload_stream(
                file_name="bad.png",
                content_type="image/png",
                stream=io.BytesIO(b"bad"),
            )
    finally:
        await client.aclose()

    assert calls == 1


@pytest.mark.asyncio
async def test_kie_upload_retries_transport_failures_then_returns_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.providers.kie_uploads.asyncio.sleep", no_sleep)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("provider timeout", request=request)

    client = KieUploadClient(
        "test-key",
        "https://upload.example",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KieProviderError, match="temporarily unavailable"):
            await client.upload_stream(
                file_name="timeout.png",
                content_type="image/png",
                stream=io.BytesIO(b"timeout-reference"),
            )
    finally:
        await client.aclose()

    assert calls == 3


@pytest.mark.asyncio
async def test_kie_upload_rejects_invalid_json_and_explicit_failure() -> None:
    responses = iter(
        [
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json={"success": False, "error": "rejected"}),
        ]
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    client = KieUploadClient(
        "test-key",
        "https://upload.example",
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KieProviderError, match="invalid JSON"):
            await client.upload_stream(
                file_name="invalid.png",
                content_type="image/png",
                stream=io.BytesIO(b"invalid"),
            )
        with pytest.raises(KieProviderError, match="Kie upload failed"):
            await client.upload_stream(
                file_name="rejected.png",
                content_type="image/png",
                stream=io.BytesIO(json.dumps({"x": 1}).encode()),
            )
    finally:
        await client.aclose()
