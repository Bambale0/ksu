from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.providers.kie import KieClient
from app.services.generations import GenerationService
from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.db.models import Generation, User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.generation_provider import GenerationProviderService
from app.services.wallet import WalletService
from app.services.generation_actions import GenerationActionService
from app.services.feed_remix import FeedRemixService
from app.services.feed import FeedService
from app.services.references import ReferenceService


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
    {"resolution": "4K"}, {"resolution": []}, {"resolution": {}}, {"aspect_ratio": "4:3"}, {"sound": False},
    {"elements": None}, {"elements": [42]},
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


@pytest.mark.parametrize(
    ("prompt", "image_urls", "video_urls", "expected"),
    [
        ("Внешность @image1. Полностью сохрани лицо", ["https://cdn.example/face.png"], [], "Внешность @image_1. Полностью сохрани лицо"),
        ("@Image1 appears", ["https://cdn.example/a.png"], [], "@image_1 appears"),
        ("Move as @video1", [], ["https://cdn.example/a.mp4"], "Move as @video_1"),
        ("@VIDEO1 follows @image2", ["https://cdn.example/a.png", "https://cdn.example/b.png"], ["https://cdn.example/a.mp4"], "@video_1 follows @image_2"),
        ("@image_1 follows @video_1", ["https://cdn.example/a.png"], ["https://cdn.example/a.mp4"], "@image_1 follows @video_1"),
    ],
)
def test_kling4_compact_aliases_normalize_for_quote_and_provider(prompt, image_urls, video_urls, expected):
    payload = {"prompt": prompt, "duration": 5, "image_urls": image_urls, "video_urls": video_urls}
    _, clean, _, _, _ = ModelCatalog.prepare(REFERENCE, payload)
    assert clean["prompt"] == expected
    assert normalize_kie_video_input("kling-4.0/reference-to-video", payload)["prompt"] == expected
    assert payload["prompt"] == prompt


@pytest.mark.parametrize("prompt", [
    "@image2", "@image0", "@image01", "@image1abc", "@image1_more", "@image1Лицо", "@image_1Лицо",
    "@video1", "@unknown", "@image1 @video2",
])
def test_kling4_compact_aliases_do_not_create_missing_or_invalid_slots(prompt):
    source = {"prompt": prompt, "duration": 5, "image_urls": ["https://cdn.example/a.png"]}
    with pytest.raises(InvalidModelParametersError, match="Undeclared reference"):
        ModelCatalog.prepare(REFERENCE, source)


def test_kling4_named_element_image1_takes_precedence_over_compact_alias():
    source = {
        "prompt": "@image1 greets @image_1",
        "duration": 5,
        "image_urls": ["https://cdn.example/scene.png"],
        "elements": [{"name": "image1", "image_urls": ["https://cdn.example/a.png", "https://cdn.example/b.png"]}],
    }
    _, clean, _, _, _ = ModelCatalog.prepare(REFERENCE, source)
    assert clean["prompt"] == "@image1 greets @image_1"


@pytest.mark.asyncio
async def test_kling4_quote_accepts_compact_image_tag_without_changing_admin_tariff(monkeypatch):
    monkeypatch.setattr(settings, "generation_pricing_json", '{"kling-4.0":{"per_second":30}}')
    spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
        None, model_id=REFERENCE, prompt="@image1. Preserve identity",
        parameters={"duration": 5, "image_urls": ["https://cdn.example/a.png"]},
    )
    assert spec.id == REFERENCE
    assert clean["prompt"] == "@image_1. Preserve identity"
    assert (cost, seconds, unit_price) == (Decimal("150.00"), 5, Decimal("30"))


@pytest.mark.asyncio
async def test_kling4_compact_image_tag_is_saved_canonical_before_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    monkeypatch.setattr(settings, "generation_pricing_json", '{"kling-4.0":{"per_second":30}}')
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Kling alias regression")
        session.add(user)
        await session.flush()
        await WalletService.credit(
            session, user_id=user.id, amount=Decimal("500"), kind="test_seed",
            reference_type="test", reference_id=str(user.id),
            idempotency_key=f"kling4-alias-seed:{user.id}",
        )
        image_url = f"https://cdn.example/{uuid.uuid4()}.png"
        session.add(UserReference(
            user_id=user.id, kind="image", status="ready",
            source="mini_app_upload", source_url=image_url,
        ))
        await session.flush()
        generations = await GenerationService.create_many(
            session, AsyncMock(), user_id=user.id, model_id=REFERENCE,
            prompt="@image1. Keep the subject", parameters={"duration": 5, "image_urls": [image_url]},
            quantity=1, commit=False, wake=False,
        )
        assert len(generations) == 1
        generation = generations[0]
        assert generation.prompt == "@image_1. Keep the subject"
        assert generation.parameters["prompt"] == "@image_1. Keep the subject"
        assert GenerationProviderService._input_for(generation)["prompt"] == "@image_1. Keep the subject"
        assert generation.cost_rox == Decimal("150.00")


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


@pytest.mark.asyncio
async def test_kling4_create_many_freezes_provider_and_prices_before_debit(monkeypatch):
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    monkeypatch.setattr(settings, "generation_pricing_json", '{"kling-4.0":{"per_second":30,"by_resolution":{"720p":30,"1080p":45}}}')
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Kling create")
        session.add(user)
        await session.flush()
        await WalletService.credit(session, user_id=user.id, amount=Decimal("1000"), kind="test_seed", reference_type="test", reference_id=str(user.id), idempotency_key=f"kling4-seed:{user.id}")
        url = f"https://cdn.example/{uuid.uuid4()}.mp4"
        session.add(UserReference(user_id=user.id, kind="video", status="ready", source="mini_app_upload", source_url=url, duration_ms=5000, probe_status="ready", size_bytes=1024))
        await session.flush()
        parameters = {"duration": 5, "resolution": "1080p", "elements": [{"name": "Hero", "video_url": url}]}
        generations = await GenerationService.create_many(session, AsyncMock(), user_id=user.id, model_id=REFERENCE, prompt="@Hero walks", parameters=parameters, quantity=2, commit=False, wake=False)
        assert len(generations) == 2
        for generation in generations:
            assert generation.provider == "kie"
            assert generation.cost_rox == Decimal("450.00")
            assert generation.parameters["_kie_model"] == "kling-4.0/reference-to-video"
            payload = GenerationProviderService._input_for(generation)
            assert payload["elements"] == parameters["elements"]
            assert payload["duration"] == 5
            assert not any(key.startswith("_") for key in payload)
        assert "current_user_id" not in session.info


@pytest.mark.parametrize("source,error", [
    ({"image_urls": ["https://cdn.example/a.png"] * 10, "elements": [{"name": f"Hero{i}", "image_urls": ["https://cdn.example/a.png"] * 2} for i in range(6)]}, "15 references"),
    ({"video_urls": ["https://cdn.example/a.mp4"] * 4, "elements": [{"name": f"Hero{i}", "video_url": "https://cdn.example/a.mp4"} for i in range(2)]}, "5 combined"),
    ({"elements": [{"name": "Hero", "image_urls": ["https://cdn.example/a.png"] * 2}], "voices": [{"name": "hero", "audio_url": "https://cdn.example/a.wav"}]}, "unique"),
    ({"elements": [{"name": "Hero", "image_urls": [], "video_url": "https://cdn.example/a.mp4"}]}, "either"),
])
def test_kling4_aggregate_limits_and_nested_exclusivity(source, error):
    with pytest.raises(InvalidModelParametersError, match=error):
        ModelCatalog.prepare(REFERENCE, {"prompt": "A sunset", **source})


@pytest.mark.parametrize("model_id,references", [
    (REFERENCE, {"elements": [{"name": f"Hero{i}", "image_urls": [f"https://author.example/{i}-a.png", f"https://author.example/{i}-b.png"]} for i in range(7)]}),
    (REFERENCE, {"elements": [{"name": f"Hero{i}", "video_url": f"https://author.example/{i}.mp4"} for i in range(3)]}),
    (KEYFRAME, {"first_frame_url": "https://author.example/first.png", "keyframe_urls": ["https://author.example/mid.png"], "last_frame_url": "https://author.example/last.png"}),
])
def test_kling4_owner_repeat_preserves_roles_without_flattening(model_id, references):
    source = Generation(kind="video", prompt="A sunset", cost_rox=Decimal("0"), parameters={"_model_id": model_id, "duration": 10, **references})
    parameters = GenerationActionService.reusable_parameters(source, model_id)
    adapted, input_url = GenerationActionService.adapt_references(source, ModelCatalog.get(model_id), parameters)
    _, clean, _, _, _ = ModelCatalog.prepare(model_id, {"prompt": source.prompt, **adapted})
    assert input_url is None
    for field, value in references.items():
        assert clean[field] == value
    assert "image_urls" not in clean
    assert "video_urls" not in clean


@pytest.mark.asyncio
async def test_kling4_hidden_feed_prepare_never_discloses_nested_author_media(monkeypatch):
    source = Generation(id=uuid.uuid4(), user_id=uuid.uuid4(), kind="video", status="succeeded", prompt="@Hero greets @Narrator", cost_rox=Decimal("0"), parameters={"_model_id": REFERENCE, "duration": 5, "elements": [{"name": "Hero", "image_urls": ["https://author.example/a.png", "https://author.example/b.png"], "voice_url": "https://author.example/bound.wav"}], "voices": [{"name": "Narrator", "audio_url": "https://author.example/narrator.wav"}]})
    async def visible(*args, **kwargs):
        return source
    async def card(*args, **kwargs):
        return {"prompt_hidden": True, "reference_images": [], "reference_videos": []}
    monkeypatch.setattr(FeedService, "assert_surface_visible", visible)
    monkeypatch.setattr(FeedService, "to_card", card)
    prepared = await FeedRemixService.prepare(None, source_generation_id=source.id, viewer_user_id=uuid.uuid4(), surface="feed")
    assert "author.example" not in json.dumps(prepared)
    assert prepared["prompt"] == ""
    assert prepared["reference_requirements"] == {"image_count": 2, "video_count": 0, "audio_count": 2, "required": True}


def test_kling4_viewer_repeat_replaces_every_nested_media_role():
    from app.services.kling4_contract import replace_kling4_references

    source = {"elements": [{"name": "Hero", "image_urls": ["https://author.example/a.png", "https://author.example/b.png"], "voice_url": "https://author.example/bound.wav"}], "voices": [{"name": "Narrator", "audio_url": "https://author.example/narrator.wav"}]}
    owned = {"image": ["https://viewer.example/a.png", "https://viewer.example/b.png"], "video": [], "audio": ["https://viewer.example/bound.wav", "https://viewer.example/narrator.wav"]}
    result = replace_kling4_references(source, {"duration": 5}, owned)
    assert "author.example" not in json.dumps(result)
    assert result["elements"][0]["name"] == "Hero"
    assert result["elements"][0]["voice_url"] == "https://viewer.example/bound.wav"
    assert result["voices"] == [{"name": "Narrator", "audio_url": "https://viewer.example/narrator.wav"}]
    ModelCatalog.prepare(REFERENCE, {"prompt": "@Hero greets @Narrator", **result})


@pytest.mark.asyncio
async def test_kling4_feed_quote_composes_owned_uploads_into_named_roles(monkeypatch):
    monkeypatch.setattr(settings, "generation_pricing_json", '{"kling-4.0":{"per_second":30,"by_resolution":{"1080p":45}}}')
    source = Generation(id=uuid.uuid4(), user_id=uuid.uuid4(), kind="video", status="succeeded", prompt="@Hero greets @Narrator", cost_rox=Decimal("0"), feed_prompt_visible=False, parameters={"_model_id": REFERENCE, "duration": 5, "resolution": "1080p", "elements": [{"name": "Hero", "image_urls": ["https://author.example/a.png", "https://author.example/b.png"]}], "voices": [{"name": "Narrator", "audio_url": "https://author.example/voice.wav"}]})
    async def visible(*args, **kwargs):
        return source
    monkeypatch.setattr(FeedService, "assert_surface_visible", visible)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Kling viewer")
        session.add(user)
        await session.flush()
        rows = [UserReference(user_id=user.id, kind=kind, status="ready", source="mini_app_upload", source_url=f"https://viewer.example/{uuid.uuid4()}.{ext}", size_bytes=1024, duration_ms=5000 if kind == "audio" else None, probe_status="ready") for kind, ext in [("image", "png"), ("image", "png"), ("audio", "wav")]]
        session.add_all(rows)
        await session.flush()
        session.info["current_user_id"] = user.id
        quote = await FeedRemixService.quote(session, source_generation_id=source.id, remix_author_id=user.id, surface="feed", prompt_override=None, reference_ids=[row.id for row in rows], confirm_own_references=True)
        assert quote["model_id"] == REFERENCE
        assert quote["retail_cost_rox"] == "225.00"
        assert "author.example" not in json.dumps(quote)


def test_kling4_keyframe_viewer_replacement_keeps_chronological_order():
    from app.services.kling4_contract import replace_kling4_references

    original = {"first_frame_url": "https://author.example/first.png", "keyframe_urls": ["https://author.example/mid.png"], "last_frame_url": "https://author.example/last.png"}
    replaced = replace_kling4_references(original, {}, {"image": ["https://viewer.example/first.png", "https://viewer.example/mid.png", "https://viewer.example/last.png"], "video": [], "audio": []})
    assert replaced == {"first_frame_url": "https://viewer.example/first.png", "keyframe_urls": ["https://viewer.example/mid.png"], "last_frame_url": "https://viewer.example/last.png"}


def test_kling4_text_feed_repeat_accepts_optional_owned_materials():
    from app.services.kling4_contract import replace_kling4_references

    replaced = replace_kling4_references({"_model_id": REFERENCE}, {"duration": 5}, {"image": ["https://viewer.example/a.png"], "video": [], "audio": ["https://viewer.example/voice.wav"]})
    assert replaced["image_urls"] == ["https://viewer.example/a.png"]
    assert replaced["voices"] == [{"name": "VoiceExtra1", "audio_url": "https://viewer.example/voice.wav"}]
    ModelCatalog.prepare(REFERENCE, {"prompt": "A sunset", **replaced})


@pytest.mark.asyncio
async def test_kling4_maximum_composition_survives_real_registration_and_feed_quote(monkeypatch):
    monkeypatch.setattr(settings, "generation_pricing_json", '{"kling-4.0":{"per_second":30}}')
    source = Generation(id=uuid.uuid4(), user_id=uuid.uuid4(), kind="video", status="succeeded", prompt="@Hero0 in @image_1", cost_rox=Decimal("0"), feed_prompt_visible=False, parameters={"_model_id": REFERENCE, "duration": 5, "image_urls": [f"https://author.example/top-{i}.png" for i in range(8)], "elements": [{"name": f"Hero{i}", "tag": "character", "image_urls": [f"https://author.example/{i}-{j}.png" for j in range(4)], "voice_url": f"https://author.example/{i}.wav"} for i in range(7)]})
    async def visible(*args, **kwargs):
        return source
    monkeypatch.setattr(FeedService, "assert_surface_visible", visible)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Kling maximum")
        session.add(user)
        await session.commit()
        ids = []
        for kind, count, extension in [("image", 36, "png"), ("audio", 7, "wav")]:
            for _ in range(count):
                row, _reused = await ReferenceService.register(session, user_id=user.id, source_url=f"https://viewer.example/{uuid.uuid4()}.{extension}", kind=kind, source="mini_app_upload")
                ids.append(row.id)
        assert len(await ReferenceService.resolve_owned(session, user_id=user.id, reference_ids=ids)) == 43
        session.info["current_user_id"] = user.id
        quote = await FeedRemixService.quote(session, source_generation_id=source.id, remix_author_id=user.id, surface="feed", prompt_override=None, reference_ids=ids, confirm_own_references=True)
        assert quote["retail_cost_rox"] == "150.00"
