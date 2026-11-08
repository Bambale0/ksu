from __future__ import annotations

import json
import uuid
from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.db.models import Generation
from app.providers.neironych_submission import SNAPSHOT_KEY, saved_body
from app.providers.neironych_video import NeironychVideoClient
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import route_options, validate_routes
from app.services.neironych_generation_provider import NeironychGenerationProviderService
from app.services.neironych_video_contracts import (
    NeironychVideoContractError, NeironychVideoUnsupportedInput,
    normalize_neironych_video_input,
)


def test_kling_route_can_be_managed_without_redeploy():
    options = route_options()
    assert ["neironych", "kie"] in options["kling-4.0"]
    assert ["kie", "neironych"] in options["kling-4.0"]
    routes = {model: choices[0] for model, choices in options.items()}
    routes["kling-4.0"] = ["neironych", "kie"]
    assert validate_routes(routes)["kling-4.0"] == ["neironych", "kie"]


@pytest.mark.parametrize("extra", [
    {"duration": True}, {"duration": 2}, {"duration": 31}, {"resolution": "480p"},
    {"resolution": []}, {"aspect_ratio": []}, {"aspect_ratio": "auto"}, {"reference_audios": [{"url": "https://cdn.example/a.wav"}]},
    {"start_image": {"url": "https://cdn.example/a.png"}}, {"generate_audio": "false"},
    {"seed": 42}, {"reference_images": [{"url": "http://private.example/a.png"}]},
])
def test_native_kling_invalid_controls_fail_before_spend(extra):
    with pytest.raises(NeironychVideoContractError):
        normalize_neironych_video_input("kling-4.0", {"prompt": "A blue cube", **extra})


def test_native_kling_keeps_order_duplicate_urls_and_silent_flag():
    body = {"prompt": "@Image 1 beside @Image 2", "duration": 3, "resolution": "1080p",
            "aspect_ratio": "adaptive", "generate_audio": False,
            "reference_images": [{"url": "https://cdn.example/a.png"}] * 2}
    before = deepcopy(body)
    assert normalize_neironych_video_input("kling-4.0", body) == body
    assert body == before


@pytest.mark.asyncio
async def test_kling_native_client_posts_frozen_wire_and_idempotency_key():
    seen = []
    async def handle(request):
        seen.append(request)
        return httpx.Response(202, json={"request_id": "kling-native-task"})
    async with httpx.AsyncClient(base_url="https://provider.example", transport=httpx.MockTransport(handle)) as http:
        client = NeironychVideoClient("synthetic", "https://provider.example", client=http)
        assert await client.create_video(model="kling-4.0", payload={
            "prompt": "A blue cube", "duration": 3, "resolution": "720p", "aspect_ratio": "9:16",
        }, idempotency_key="kling-test-native") == "kling-native-task"
    assert seen[0].url.path == "/v1/videos/generations"
    assert seen[0].headers["Idempotency-Key"] == "kling-test-native"
    assert json.loads(seen[0].content)["model"] == "kling-4.0"
    assert seen[0].extensions["timeout"]["read"] == settings.neironych_request_timeout_seconds


def generation(extra=None):
    return Generation(id=uuid.uuid4(), user_id=uuid.uuid4(), kind="video", prompt="A blue cube",
        cost_rox=Decimal("0"), provider="neironych", status="queued", parameters={
            "_model_id": "kling-4.0", "_kie_model": "kling-4.0/reference-to-video",
            "_provider_route": ["neironych", "kie"], "_provider_route_index": 0,
            "prompt": "A blue cube", "duration": 3, "resolution": "720p", **(extra or {}),
        })


@pytest.mark.asyncio
async def test_kling_service_translates_roles_and_freezes_original_request(monkeypatch):
    async def resolve(session, gen, raw):
        return raw
    monkeypatch.setattr(GenerationProviderService, "_resolve_workflow_media_input", resolve)
    gen = generation({"prompt": "@image_1 and @image_2 follow @video_1", "aspect_ratio": "auto",
        "image_urls": ["https://cdn.example/a.png"] * 2, "video_urls": ["https://cdn.example/v.mp4"]})
    before = deepcopy(gen.parameters)
    await NeironychGenerationProviderService._freeze_new_submission(AsyncMock(), gen)
    snapshot = gen.parameters[SNAPSHOT_KEY]
    body = json.loads(saved_body(snapshot, model="kling-4.0",
        key=f"generation:{gen.id}:provider:0", base_url=settings.neironych_api_base_url))
    assert body == {"model": "kling-4.0", "prompt": "@Image 1 and @Image 2 follow @Video 1",
        "duration": 3, "resolution": "720p", "aspect_ratio": "adaptive",
        "reference_images": [{"url": "https://cdn.example/a.png"}] * 2,
        "reference_videos": [{"url": "https://cdn.example/v.mp4"}]}
    assert {k:v for k,v in gen.parameters.items() if k != SNAPSHOT_KEY} == before
    # Subsequent config/raw changes must not rewrite an already frozen paid request.
    gen.parameters = {**gen.parameters, "prompt": "Changed"}
    await NeironychGenerationProviderService._freeze_new_submission(AsyncMock(), gen)
    assert gen.parameters[SNAPSHOT_KEY] == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("controls", [
    {"elements": [{"name": "Hero", "image_urls": ["https://cdn.example/a.png"] * 2}]},
    {"voices": [{"name": "Voice", "audio_url": "https://cdn.example/a.wav"}]},
    {"keep_original_sound": True}, {"keep_original_sound": False}, {"aspect_ratio": "auto"},
])
async def test_kling_unrepresentable_controls_do_not_freeze_or_mutate(monkeypatch, controls):
    async def resolve(session, gen, raw):
        return raw
    monkeypatch.setattr(GenerationProviderService, "_resolve_workflow_media_input", resolve)
    gen = generation(controls)
    before = deepcopy(gen.parameters)
    with pytest.raises(NeironychVideoUnsupportedInput):
        await NeironychGenerationProviderService._freeze_new_submission(AsyncMock(), gen)
    assert gen.parameters == before

@pytest.mark.asyncio
async def test_kling_service_handles_registered_model_and_image_role(monkeypatch):
    async def resolve(session, gen, raw):
        return raw
    monkeypatch.setattr(GenerationProviderService, "_resolve_workflow_media_input", resolve)
    gen = generation({"prompt": "@image_1", "image_urls": ["https://cdn.example/a.png"]})
    assert NeironychGenerationProviderService.handles(gen)
    await NeironychGenerationProviderService._freeze_new_submission(AsyncMock(), gen)
    body = json.loads(saved_body(gen.parameters[SNAPSHOT_KEY], model="kling-4.0",
        key=f"generation:{gen.id}:provider:0", base_url=settings.neironych_api_base_url))
    assert body["prompt"] == "@Image 1"

@pytest.mark.asyncio
@pytest.mark.parametrize("unsupported", [False, True])
async def test_kling_submission_or_pre_spend_fallback_preserves_source(monkeypatch, unsupported):
    from test_neironych_provider_fallbacks import _generation
    from app.db.session import SessionFactory

    posted = []
    task_id = "kling-paid-task-" + uuid.uuid4().hex
    class VideoClient:
        def __init__(self, *args, **kwargs):
            pass
        async def aclose(self):
            pass
        async def create_video(self, **kwargs):
            posted.append(kwargs)
            return task_id
    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", VideoClient)
    params = {"prompt": "A blue cube", "duration": 3, "resolution": "720p", "aspect_ratio": "9:16"}
    if unsupported:
        params["voices"] = [{"name": "Voice", "audio_url": "https://cdn.example/voice.wav"}]
    gen = await _generation(model_id="kling-4.0", route=["neironych", "kie"], parameters=params)
    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, gen.id)
        if unsupported:
            assert not posted
            assert result.provider == "kie"
            assert result.status == "retry"
            assert result.parameters["voices"] == params["voices"]
            assert result.parameters["_provider_route_index"] == 1
            assert SNAPSHOT_KEY not in result.parameters
        else:
            assert result.provider == "neironych"
            assert result.status == "generating"
            assert result.external_id == task_id
            assert json.loads(posted[0]["request_body"]) == {"model": "kling-4.0", **params}
            await NeironychGenerationProviderService.submit(session, gen.id)
            assert len(posted) == 1

@pytest.mark.asyncio
async def test_kling_registry_addition_preserves_older_route_migration():
    from types import SimpleNamespace
    from app.services.generation_provider_routing import configured_routes

    routes = {model: choices[0] for model, choices in route_options().items()
              if model not in {"grok-video-1.5", "grok-video-t2v", "grok-video-i2v", "kling-4.0"}}
    for model in ("nano-banana-2", "nano-banana-2-lite", "gpt-image-2-t2i", "gpt-image-2-i2i"):
        routes[model] = ["nexus", "kie"]
    routes["seedream-5-pro-t2i"] = ["kie", "nexus"]
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(value={"revision": 7, "routes": routes})
    result = await configured_routes(session)
    assert result["routes"]["nano-banana-2"] == ["nexus", "neironych", "kie"]
    assert result["routes"]["seedream-5-pro-t2i"] == ["kie", "nexus"]
    assert result["routes"]["kling-4.0"] == ["kie", "neironych"]
    assert result["revision"] == 7

@pytest.mark.asyncio
async def test_kling_valid_http_reference_is_a_capability_fallback(monkeypatch):
    async def resolve(session, gen, raw):
        return raw
    monkeypatch.setattr(GenerationProviderService, "_resolve_workflow_media_input", resolve)
    gen = generation({"image_urls": ["http://cdn.example/a.png"]})
    before = deepcopy(gen.parameters)
    with pytest.raises(NeironychVideoUnsupportedInput):
        await NeironychGenerationProviderService._freeze_new_submission(AsyncMock(), gen)
    assert gen.parameters == before

@pytest.mark.asyncio
async def test_kling_http_reference_falls_back_without_a_provider_post(monkeypatch):
    from test_neironych_provider_fallbacks import _generation
    from app.db.session import SessionFactory
    client = AsyncMock()
    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient",
                        lambda *args, **kwargs: client)
    url = "http://cdn.example/a.png"
    gen = await _generation(model_id="kling-4.0", route=["neironych", "kie"],
        parameters={"prompt": "A cube", "duration": 3, "image_urls": [url]})
    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, gen.id)
        assert result.provider == "kie" and result.status == "retry"
        assert result.parameters["image_urls"] == [url]
        assert SNAPSHOT_KEY not in result.parameters
        client.create_video.assert_not_called()
