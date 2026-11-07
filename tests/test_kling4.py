from __future__ import annotations

import json
import uuid
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.providers.kie import KieClient
from app.services.generations import GenerationService
from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.db.models import User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory


REFERENCE = "kling-4.0"
KEYFRAME = "kling-4.0-keyframe"


@pytest.mark.parametrize("model_id,provider", [
    (REFERENCE, "kling-4.0/reference-to-video"),
    (KEYFRAME, "kling-4.0/keyframe-to-video"),
])
def test_kling4_catalog_and_ui_offer_current_kie_contract(model_id, provider):
    spec = ModelCatalog.get(model_id)
    assert spec.kie_model == provider
    assert (spec.min_seconds, spec.max_seconds) == (3, 30)
    schema = build_public_model_ui_schema(spec.public_dict())
    fields = {field["name"]: field for field in schema["fields"]}
    assert fields["resolution"]["suggestions"] == ["720p", "1080p"]
    assert fields["duration"]["suggestions"] == list(range(3, 31))
    assert fields["prompt"]["max_length"] == 8000
    assert "21:9" in fields["aspect_ratio"]["suggestions"]
    assert schema["defaults"]["duration"] == 5
    assert "billing_seconds" not in schema


def test_kling4_keyframes_keep_order_and_validate_duration_dependent_frame_count():
    payload = {"prompt": "@first_frame to @keyframe_1 then @last_frame", "duration": 3,
               "first_frame_url": "https://cdn.example/first.png",
               "keyframe_urls": ["https://cdn.example/middle.png"],
               "last_frame_url": "https://cdn.example/last.png"}
    _, clean, _, seconds, _ = ModelCatalog.prepare(KEYFRAME, payload)
    assert clean["keyframe_urls"] == payload["keyframe_urls"]
    assert seconds == 3
    with pytest.raises(InvalidModelParametersError, match="frames"):
        ModelCatalog.prepare(KEYFRAME, {**payload, "keyframe_urls": ["https://cdn.example/a.png"] * 3})
    with pytest.raises(InvalidModelParametersError, match="first_frame"):
        ModelCatalog.prepare(KEYFRAME, {"prompt": "x", "last_frame_url": payload["last_frame_url"]})


@pytest.mark.parametrize("extra", [
    {"duration": True}, {"duration": 3.5}, {"duration": 31}, {"duration": 2},
    {"resolution": "4K"}, {"aspect_ratio": "4:3"}, {"sound": False},
    {"prompt": "x" * 8001}, {"image_urls": [42]}, {"video_urls": "https://cdn.example/v.mp4"},
    {"elements": [{"name": "image_1", "image_urls": ["https://cdn.example/a.png"] * 2}]},
    {"elements": [{"name": "Hero", "image_urls": ["https://cdn.example/a.png"]}]},
    {"voices": [{"name": "Hero", "audio_url": "https://cdn.example/a.mp3"}] * 2},
    {"prompt": "@missing runs"}, {"prompt": "@image_2", "image_urls": ["https://cdn.example/a.png"]},
])
def test_kling4_invalid_payload_is_blocked_at_both_public_and_provider_boundaries(extra):
    source = {"prompt": "A sunset", "duration": 5, **extra}
    with pytest.raises(InvalidModelParametersError):
        ModelCatalog.prepare(REFERENCE, source)
    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input("kling-4.0/reference-to-video", source)


def test_kling4_omni_accepts_named_subjects_and_voices_without_mutating_input():
    source = {"prompt": "@Hero greets @Narrator near @image_1", "duration": 30,
              "image_urls": ["https://cdn.example/scene.png"],
              "elements": [{"name": "Hero", "image_urls": ["https://cdn.example/a.png", "https://cdn.example/b.png"], "tag": "character"}],
              "voices": [{"name": "Narrator", "audio_url": "https://cdn.example/voice.mp3"}]}
    before = json.dumps(source)
    normalized = normalize_kie_video_input("kling-4.0/reference-to-video", source)
    assert normalized["elements"] == source["elements"]
    assert normalized["voices"] == source["voices"]
    assert normalized["duration"] == 30
    assert json.dumps(source) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", [REFERENCE, KEYFRAME])
async def test_kling4_quote_uses_admin_resolution_prices(model_id):
    old = settings.generation_pricing_json
    settings.generation_pricing_json = json.dumps({model_id: {"per_second": 30, "by_resolution": {"720p": 30, "1080p": 45}}})
    try:
        for resolution, expected in [("720p", Decimal("150.00")), ("1080p", Decimal("225.00"))]:
            _, clean, cost, seconds, _ = await GenerationService.prepare_request(
                None, model_id=model_id, prompt="A sunset", parameters={"duration": 5, "resolution": resolution})
            assert (cost, seconds, clean["resolution"]) == (expected, 5, resolution)
    finally:
        settings.generation_pricing_json = old


@pytest.mark.asyncio
async def test_kling4_client_posts_exact_model_input_and_callback():
    captured = []
    async def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"code": 200, "data": {"taskId": "kling4-task"}})
    client = KieClient("synthetic-test-key")
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url="https://api.kie.ai", transport=httpx.MockTransport(handle))
    try:
        task = await client.create_task(model="kling-4.0/keyframe-to-video", input_data={"prompt": "A sunset", "duration": 30}, callback_url="https://roxy.example/callback")
    finally:
        await client.aclose()
    assert task == "kling4-task"
    assert captured == [{"model": "kling-4.0/keyframe-to-video", "callBackUrl": "https://roxy.example/callback", "input": {"prompt": "A sunset", "duration": 30, "resolution": "720p"}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
async def test_kling4_owned_video_and_video_subject_double_retail_price(nested):
    old = settings.generation_pricing_json
    settings.generation_pricing_json = '{"kling-4.0":{"per_second":30,"by_resolution":{"720p":30,"1080p":45}}}'
    try:
        async with SessionFactory() as session:
            user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Kling test")
            session.add(user)
            await session.flush()
            url = f"https://cdn.example/{uuid.uuid4()}.mp4"
            row = UserReference(user_id=user.id, kind="video", status="ready", source="mini_app_upload", source_url=url, duration_ms=5000, probe_status="ready", size_bytes=1024)
            session.add(row)
            await session.flush()
            session.info["current_user_id"] = user.id
            references = {"elements": [{"name": "Hero", "video_url": url}]} if nested else {"video_urls": [url]}
            _, _, cost, seconds, price = await GenerationService.prepare_request(session, model_id=REFERENCE, prompt="A sunset", parameters={"duration": 5, "resolution": "1080p", **references})
            assert (cost, seconds, price) == (Decimal("450.00"), 5, Decimal("90"))
            row.duration_ms = 31000
            await session.flush()
            with pytest.raises(InvalidModelParametersError, match="seconds"):
                await GenerationService.prepare_request(session, model_id=REFERENCE, prompt="A sunset", parameters={"duration": 5, **references})
            row.duration_ms = 5000
            await session.flush()
            session.info["current_user_id"] = uuid.uuid4()
            with pytest.raises(InvalidModelParametersError, match="verified"):
                await GenerationService.prepare_request(session, model_id=REFERENCE, prompt="A sunset", parameters={"duration": 5, **references})
    finally:
        settings.generation_pricing_json = old
