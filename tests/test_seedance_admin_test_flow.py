from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.bot.handlers.seedance_test import _model_keyboard, _seedance_default_payload
from app.providers.neironych_video import (
    NeironychProviderError,
    NeironychVideoClient,
    SEEDANCE_TEST_MODELS,
    is_failure_status,
    is_success_status,
    resolve_seedance_model,
)
from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def test_admin_test_model_picker_exposes_nano_and_both_seedance_versions() -> None:
    callbacks = _callbacks(_model_keyboard())
    assert "nexus-test:model:nano-banana-pro" in callbacks
    assert "nexus-test:model:seedance-2.0" in callbacks
    assert "nexus-test:model:seedance-2.5" in callbacks
    assert SEEDANCE_TEST_MODELS == ("seedance-2.0", "seedance-2.5")


@pytest.mark.asyncio
async def test_seedance_client_uses_documented_async_video_contract_and_raw_passthrough(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer secret"

        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": "seedance-2.0"}, {"id": "seedance-2.5"}]},
            )
        if request.method == "POST":
            assert request.url.path == "/v1/videos/generations"
            assert request.headers["Idempotency-Key"] == "ksu-test-12345678"
            payload = json.loads(request.content)
            assert payload == {
                "model": "seedance-2.5",
                "prompt": "cinematic",
                "duration": 12,
                "aspect_ratio": "9:16",
                "provider_future_option": {"enabled": True},
            }
            return httpx.Response(202, json={"request_id": "video-123"})
        if request.url.path == "/v1/videos/video-123/content":
            return httpx.Response(200, content=b"fake-mp4", headers={"content-type": "video/mp4"})

        assert request.url.path == "/v1/videos/video-123"
        return httpx.Response(
            200,
            json={"request_id": "video-123", "status": "completed"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient(
            "secret",
            "https://provider.example",
            client=http_client,
        )
        assert await client.list_models() == ["seedance-2.0", "seedance-2.5"]
        request_id = await client.create_video(
            model="seedance-2.5",
            payload={
                "model": "attempted-override",
                "prompt": "cinematic",
                "duration": 12,
                "aspect_ratio": "9:16",
                "provider_future_option": {"enabled": True},
            },
            idempotency_key="ksu-test-12345678",
        )
        assert request_id == "video-123"
        status, error, _payload = await client.get_video(request_id)
        assert status == "completed"
        assert error == ""

        target = tmp_path / "result.mp4"
        content_type = await client.download_content_to(
            request_id,
            target,
            max_bytes=1024,
        )

    assert content_type == "video/mp4"
    assert target.read_bytes() == b"fake-mp4"
    assert len(requests) == 4


class _InterruptedAsyncStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk
        raise httpx.RemoteProtocolError("peer closed connection early")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_seedance_download_resumes_from_last_written_byte_after_disconnect(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v1/videos/video-resume/content"
        assert request.headers["Authorization"] == "Bearer secret"
        range_header = request.headers.get("Range")
        if len(requests) == 1:
            assert range_header == "bytes=0-262143"
            return httpx.Response(
                206,
                headers={
                    "content-type": "video/mp4",
                    "content-range": "bytes 0-7/8",
                    "content-length": "8",
                    "accept-ranges": "bytes",
                },
                stream=_InterruptedAsyncStream([b"abcd"]),
            )
        assert range_header == "bytes=4-7"
        return httpx.Response(
            206,
            headers={
                "content-type": "video/mp4",
                "content-range": "bytes 4-7/8",
                "content-length": "4",
                "accept-ranges": "bytes",
            },
            content=b"efgh",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient(
            "secret",
            "https://provider.example",
            client=http_client,
        )
        target = tmp_path / "resume.mp4"
        content_type = await client.download_content_to(
            "video-resume",
            target,
            max_bytes=1024,
        )

    assert content_type == "video/mp4"
    assert target.read_bytes() == b"abcdefgh"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_neironych_media_upload_uses_ticket_then_direct_storage_put() -> None:
    content = b"telegram-photo-bytes"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/media/uploads"
            assert request.headers["Authorization"] == "Bearer secret"
            assert request.headers["Content-Type"].startswith("application/json")
            assert json.loads(request.content) == {
                "model": "seedance-2.5",
                "type": "image",
                "content_type": "image/jpeg",
                "size_bytes": len(content),
            }
            return httpx.Response(
                200,
                json={
                    "upload_url": "https://storage.example/presigned/photo",
                    "media_url": "https://cdn.example/reference/photo.jpg",
                },
            )

        assert request.method == "PUT"
        assert request.url == httpx.URL("https://storage.example/presigned/photo")
        assert "Authorization" not in request.headers
        assert request.headers["Content-Type"] == "image/jpeg"
        assert request.content == content
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="https://provider.example",
            headers={"Authorization": "Bearer api-client-default"},
        ) as http_client,
        httpx.AsyncClient(transport=transport) as storage_client,
    ):
        client = NeironychVideoClient(
            "secret",
            "https://provider.example",
            client=http_client,
            storage_client=storage_client,
        )
        media_url = await client.upload_media(
            model="seedance-2.5",
            media_type="image",
            content=content,
            mime_type="image/jpeg",
        )

    assert media_url == "https://cdn.example/reference/photo.jpg"
    assert [request.method for request in requests] == ["POST", "PUT"]


@pytest.mark.asyncio
async def test_seedance_client_rejects_unsupported_model_and_short_idempotency_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient("secret", "https://provider.example", client=http_client)
        with pytest.raises(NeironychProviderError, match="Unsupported"):
            await client.create_video(
                model="other",
                payload={"prompt": "x"},
                idempotency_key="12345678",
            )
        with pytest.raises(NeironychProviderError, match="8..160"):
            await client.create_video(
                model="seedance-2.0",
                payload={"prompt": "x"},
                idempotency_key="short",
            )


@pytest.mark.asyncio
async def test_seedance_provider_error_is_bounded_and_redacts_long_tokens() -> None:
    secret = "a" * 64

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"message": f"bad media https://cdn.example/file?token={secret}"}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.example",
    ) as http_client:
        client = NeironychVideoClient("secret", "https://provider.example", client=http_client)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_video(
                model="seedance-2",
                payload={"prompt": "x"},
                idempotency_key="12345678-valid",
            )

    assert caught.value.status_code == 422
    assert secret not in str(caught.value)
    assert "[REDACTED]" in str(caught.value)


def test_seedance_model_resolver_accepts_live_aliases() -> None:
    assert resolve_seedance_model("seedance-2.0", ["seedance-2"]) == "seedance-2"
    assert (
        resolve_seedance_model(
            "seedance-2.0",
            ["bytedance/seedance-2.0"],
        )
        == "bytedance/seedance-2.0"
    )
    assert resolve_seedance_model("seedance-2.5", ["seedance-2.5"]) == "seedance-2.5"
    assert resolve_seedance_model("seedance-2.5", ["other"]) is None


def test_seedance_status_normalization() -> None:
    assert is_success_status("completed")
    assert is_success_status("DONE")
    assert is_failure_status("failed")
    assert is_failure_status("cancelled")
    assert not is_success_status("processing")
    assert not is_failure_status("queued")


def test_seedance_test_is_durable_and_registered_before_customer_router() -> None:
    dispatcher = Path("app/bot/dispatcher.py").read_text(encoding="utf-8")
    assert "seedance_test.router" in dispatcher
    assert dispatcher.index("include_router(seedance_test.router)") < dispatcher.index(
        "include_router(launcher.router)"
    )

    handler = Path("app/bot/handlers/seedance_test.py").read_text(encoding="utf-8")
    assert "SeedanceAdminTaskService.enqueue" in handler
    assert "NEIRONYCH_API_KEY" in handler
    assert "json.loads" in handler
    assert 'payload["model"] = model_name' in handler
    assert 'candidate["prompt"] = prompt' in handler
    assert "normalize_neironych_video_input(model_name, candidate)" in handler

    worker = Path("app/workers/nexus_test.py").read_text(encoding="utf-8")
    assert "SeedanceAdminTaskService.claim" in worker
    assert "SeedanceAdminTaskService.process" in worker

    service = Path("app/services/seedance_admin_tasks.py").read_text(encoding="utf-8")
    assert "client.list_models()" in service
    assert "client.create_video(" in service
    assert "client.get_video(" in service
    assert "client.download_content_to(" in service


def test_seedance_default_payload_contains_only_documented_minimum_fields() -> None:
    payload = _seedance_default_payload()
    assert payload == {
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5,
    }
    forbidden = {
        "generate_audio",
        "return_last_frame",
        "output_format",
        "web_search",
        "nsfw_checker",
        "fixed_lens",
    }
    assert forbidden.isdisjoint(payload)


def test_neironych_normalizer_strips_known_illegal_legacy_fields() -> None:
    payload = normalize_neironych_video_input(
        "seedance-2.5",
        {
            "prompt": "cinematic",
            "duration": "12",
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "generate_audio": False,
            "return_last_frame": False,
            "output_format": "mp4",
            "web_search": False,
            "nsfw_checker": True,
            "fixed_lens": False,
            "provider_future_option": {"enabled": True},
        },
    )
    assert payload == {
        "prompt": "cinematic",
        "duration": 12,
        "resolution": "720p",
        "aspect_ratio": "9:16",
        "provider_future_option": {"enabled": True},
    }


@pytest.mark.parametrize(
    ("model", "field", "value", "message"),
    [
        ("seedance-2.0", "duration", 3, "4"),
        ("seedance-2.0", "duration", 16, "15"),
        ("seedance-2.5", "duration", 31, "30"),
        ("seedance-2.0", "resolution", "8k", "resolution"),
        ("seedance-2.5", "resolution", "4k", "resolution"),
        ("seedance-2.5", "aspect_ratio", "2:1", "aspect_ratio"),
        ("seedance-2.5", "aspect_ratio", "adaptive", "start_image"),
    ],
)
def test_neironych_normalizer_rejects_invalid_documented_ranges_and_enums(
    model: str,
    field: str,
    value: object,
    message: str,
) -> None:
    payload = {
        "prompt": "cinematic",
        "duration": 8,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }
    payload[field] = value
    with pytest.raises(NeironychVideoContractError, match=message):
        normalize_neironych_video_input(model, payload)


def test_neironych_normalizer_allows_adaptive_only_with_frame_input() -> None:
    payload = normalize_neironych_video_input(
        "seedance-2.5",
        {
            "prompt": "animate frame",
            "duration": 8,
            "resolution": "1080p",
            "aspect_ratio": "adaptive",
            "start_image": {"url": "https://cdn.example/start.jpg"},
        },
    )
    assert payload["aspect_ratio"] == "adaptive"
    assert payload["start_image"] == {"url": "https://cdn.example/start.jpg"}


def test_neironych_prompt_limit_is_40000_utf8_bytes_not_characters() -> None:
    allowed = normalize_neironych_video_input(
        "seedance-2.0",
        {
            "prompt": "я" * 20_000,
            "duration": 8,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )
    assert len(allowed["prompt"].encode("utf-8")) == 40_000

    with pytest.raises(NeironychVideoContractError, match="40 000"):
        normalize_neironych_video_input(
            "seedance-2.0",
            {
                "prompt": "я" * 20_001,
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )


def test_neironych_prompt_reference_integrity_rejects_missing_typed_reference() -> None:
    with pytest.raises(NeironychVideoContractError, match="@Image2"):
        normalize_neironych_video_input(
            "seedance-2.5",
            {
                "prompt": "Keep @Image 1 and @Image 2 consistent",
                "duration": 8,
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "reference_images": [{"url": "https://cdn.example/one.jpg"}],
            },
        )


def test_neironych_normalizer_converts_legacy_reference_url_aliases() -> None:
    payload = normalize_neironych_video_input(
        "seedance-2.0",
        {
            "prompt": "Use @Image 1 and @Video 1",
            "duration": 8,
            "resolution": "4K",
            "aspect_ratio": "21:9",
            "reference_image_urls": ["https://cdn.example/one.jpg"],
            "reference_video_urls": ["https://cdn.example/motion.mp4"],
        },
    )
    assert payload["resolution"] == "4k"
    assert payload["reference_images"] == [{"url": "https://cdn.example/one.jpg"}]
    assert payload["reference_videos"] == [{"url": "https://cdn.example/motion.mp4"}]
    assert "reference_image_urls" not in payload
    assert "reference_video_urls" not in payload
