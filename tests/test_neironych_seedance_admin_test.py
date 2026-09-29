from __future__ import annotations

import importlib
import json
from pathlib import Path

import httpx
import pytest


PROVIDER_PATH = Path("app/providers/neironych.py")
HANDLER_PATH = Path("app/bot/handlers/nexus_test.py")
WORKER_PATH = Path("app/workers/nexus_test.py")
COMPOSE_PATH = Path("docker-compose.yml")


def _provider():
    if not PROVIDER_PATH.exists():
        pytest.skip("Neironych provider adapter is not implemented yet")
    return importlib.import_module("app.providers.neironych")


def test_neironych_provider_adapter_exists() -> None:
    assert PROVIDER_PATH.exists(), "Seedance admin test requires a dedicated Neironych adapter"


def test_admin_test_exposes_seedance_20_and_25_model_selection() -> None:
    source = HANDLER_PATH.read_text(encoding="utf-8")
    assert "seedance-2.0" in source
    assert "seedance-2.5" in source
    assert "nexus-test:model:" in source
    assert "nexus-test:seedance-mode:" in source


@pytest.mark.asyncio
async def test_neironych_seedance_25_reference_payload_and_idempotency() -> None:
    provider = _provider()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v1/videos/generations"
        assert request.headers["Authorization"] == "Bearer partner-key"
        assert request.headers["Idempotency-Key"] == "seedance-test-idem-0001"
        assert json.loads(request.content) == {
            "model": "seedance-2.5",
            "prompt": "Keep @Image 1, motion from @Video 1 and music from @Audio 1",
            "duration": 12,
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "reference_images": [{"url": "https://roxy.test/i.jpg"}],
            "reference_videos": [{"url": "https://roxy.test/v.mp4"}],
            "reference_audios": [{"url": "https://roxy.test/a.mp3"}],
            "omni_reference_task_type": "reference",
            "generate_audio": True,
        }
        return httpx.Response(202, json={"request_id": "req-25-ref"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.xn--e1aikcel5c5a.online",
    ) as http_client:
        client = provider.NeironychClient("partner-key", client=http_client)
        request_id = await client.create_seedance_video(
            model="seedance-2.5",
            prompt="Keep @Image 1, motion from @Video 1 and music from @Audio 1",
            duration=12,
            resolution="1080p",
            aspect_ratio="9:16",
            reference_images=["https://roxy.test/i.jpg"],
            reference_videos=["https://roxy.test/v.mp4"],
            reference_audios=["https://roxy.test/a.mp3"],
            task_type="reference",
            generate_audio=True,
            idempotency_key="seedance-test-idem-0001",
        )

    assert request_id == "req-25-ref"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_neironych_seedance_25_edit_uses_source_following_contract() -> None:
    provider = _provider()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"request_id": "req-edit"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test",
    ) as http_client:
        client = provider.NeironychClient("partner-key", client=http_client)
        await client.create_seedance_video(
            model="seedance-2.5",
            prompt="Replace the sky in @Video 1",
            duration=-1,
            resolution="720p",
            aspect_ratio="adaptive",
            reference_videos=["https://roxy.test/source.mp4"],
            task_type="edit",
            idempotency_key="seedance-test-idem-0002",
        )

    assert captured["model"] == "seedance-2.5"
    assert captured["duration"] == -1
    assert captured["aspect_ratio"] == "adaptive"
    assert captured["omni_reference_task_type"] == "edit"
    assert captured["reference_videos"] == [{"url": "https://roxy.test/source.mp4"}]


@pytest.mark.asyncio
async def test_neironych_seedance_20_supports_4k_and_documented_reference_limits() -> None:
    provider = _provider()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"request_id": "req-20"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test",
    ) as http_client:
        client = provider.NeironychClient("partner-key", client=http_client)
        await client.create_seedance_video(
            model="seedance-2.0",
            prompt="Use all references",
            duration=15,
            resolution="4k",
            aspect_ratio="21:9",
            reference_images=[f"https://roxy.test/i-{i}.jpg" for i in range(9)],
            reference_videos=[f"https://roxy.test/v-{i}.mp4" for i in range(3)],
            idempotency_key="seedance-test-idem-0003",
        )

    assert captured["resolution"] == "4k"
    assert len(captured["reference_images"]) == 9
    assert len(captured["reference_videos"]) == 3


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "model": "seedance-2.5",
                "prompt": "edit",
                "duration": -1,
                "resolution": "720p",
                "aspect_ratio": "adaptive",
                "task_type": "edit",
            },
            "reference video",
        ),
        (
            {
                "model": "seedance-2.5",
                "prompt": "frames",
                "duration": 6,
                "resolution": "720p",
                "aspect_ratio": "adaptive",
                "start_image": "https://roxy.test/start.jpg",
                "reference_images": ["https://roxy.test/ref.jpg"],
            },
            "frame mode",
        ),
        (
            {
                "model": "seedance-2.0",
                "prompt": "audio only",
                "duration": 5,
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "reference_audios": ["https://roxy.test/a.mp3"],
            },
            "audio",
        ),
    ],
)
@pytest.mark.asyncio
async def test_neironych_rejects_invalid_seedance_mode_combinations(
    kwargs: dict[str, object],
    message: str,
) -> None:
    provider = _provider()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: pytest.fail("request must not be sent")),
        base_url="https://provider.test",
    ) as http_client:
        client = provider.NeironychClient("partner-key", client=http_client)
        with pytest.raises(provider.NeironychProviderError, match=message):
            await client.create_seedance_video(
                **kwargs,
                idempotency_key="seedance-test-idem-0004",
            )


@pytest.mark.asyncio
async def test_neironych_poll_and_content_use_authenticated_video_endpoints(tmp_path: Path) -> None:
    provider = _provider()
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer partner-key"
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"fake-mp4", headers={"content-type": "video/mp4"})
        return httpx.Response(
            200,
            json={"request_id": "req-1", "status": "succeeded"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test",
    ) as http_client:
        client = provider.NeironychClient("partner-key", client=http_client)
        task = await client.get_video("req-1")
        target = tmp_path / "result.mp4"
        await client.download_video("req-1", target)

    assert task.request_id == "req-1"
    assert task.status == "succeeded"
    assert target.read_bytes() == b"fake-mp4"
    assert calls == [
        ("GET", "/v1/videos/req-1"),
        ("GET", "/v1/videos/req-1/content"),
    ]


def test_seedance_admin_flow_covers_full_documented_modes_and_ranges() -> None:
    source = HANDLER_PATH.read_text(encoding="utf-8")
    assert "text" in source
    assert "reference" in source
    assert "frames" in source
    assert "edit" in source
    assert "SEEDANCE_20_MAX_DURATION" in source
    assert "SEEDANCE_25_MAX_DURATION" in source
    assert '"4k"' in source
    assert '"1080p"' in source
    assert "reference_audios" in source or "audio" in source
    assert "start_image" in source
    assert "end_image" in source


def test_admin_test_worker_accepts_neironych_without_nexus_and_shares_reference_storage() -> None:
    worker = WORKER_PATH.read_text(encoding="utf-8")
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "neironych_api_key" in worker
    assert "nexus_api_key" in worker
    assert "./static/uploads:/app/static/uploads" in compose
