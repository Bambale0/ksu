"""Kling 4.0 provider selection for original sound and supported references.

The supplier contract only supports retaining original video sound through KIE.
Neironych treats omission / false as native generated-audio behavior.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
import pytest

from app.services.generation_provider_routing import select_kling4_route
from app.services.neironych_video_contracts import (
    NeironychVideoUnsupportedInput,
    prepare_neironych_kling_input,
)
from app.services.generations import GenerationService


BASE = {
    "prompt": "@image_1 follows @video_1",
    "duration": 10,
    "resolution": "720p",
    "aspect_ratio": "9:16",
    "image_urls": ["https://cdn.example/photo.png"],
    "video_urls": ["https://cdn.example/motion.mp4"],
}


@pytest.mark.parametrize("value", [None, False])
def test_generated_audio_is_compatible_with_neironych(value):
    original = dict(BASE)
    if value is not None:
        original["keep_original_sound"] = value
    prepared = prepare_neironych_kling_input(original)
    assert "keep_original_sound" not in prepared
    assert prepared["reference_videos"] == [{"url": BASE["video_urls"][0]}]
    assert original.get("keep_original_sound") == value


@pytest.mark.parametrize("value", [None, False])
def test_no_video_input_has_no_original_sound_semantics(value):
    original = {"prompt": "A blue cube", "duration": 3, "resolution": "720p"}
    if value is not None:
        original["keep_original_sound"] = value
    prepared = prepare_neironych_kling_input(original)
    assert "keep_original_sound" not in prepared


def test_original_sound_true_must_not_be_silently_dropped():
    with pytest.raises(NeironychVideoUnsupportedInput):
        prepare_neironych_kling_input({**BASE, "keep_original_sound": True})


@pytest.mark.parametrize("controls,reason", [
    ({"keep_original_sound": True, "video_urls": BASE["video_urls"]}, "original_sound"),
    ({"elements": [{"name": "Subject"}]}, "elements"),
    ({"voices": [{"name": "Actor"}]}, "voices"),
])
def test_incompatible_kling_controls_select_kie_directly(controls, reason):
    route, result = select_kling4_route("kling-4.0", controls, ("neironych", "kie"))
    assert route == ("kie",)
    assert result == reason


@pytest.mark.parametrize("controls", [
    {"keep_original_sound": False, "video_urls": BASE["video_urls"]},
    {"keep_original_sound": True, "image_urls": BASE["image_urls"]},
    {"image_urls": BASE["image_urls"], "video_urls": BASE["video_urls"]},
])
def test_nonoperative_audio_flag_does_not_force_kie(controls):
    route, reason = select_kling4_route("kling-4.0", controls, ("neironych", "kie"))
    assert route == ("neironych", "kie")
    assert reason is None


def test_only_kie_is_compatible_with_original_sound():
    assert select_kling4_route("kling-4.0", {
        "keep_original_sound": True, "video_urls": BASE["video_urls"]
    }, ("kie", "neironych")) == (("kie",), "original_sound")
    with pytest.raises(ValueError, match="KIE"):
        select_kling4_route("kling-4.0", {
            "keep_original_sound": True, "video_urls": BASE["video_urls"]
        }, ("neironych",))


def test_keyframe_and_other_models_are_untouched():
    for model in ("kling-4.0-keyframe", "seedance-2.5"):
        assert select_kling4_route(model, {"keep_original_sound": True, "video_urls": BASE["video_urls"]},
                                   ("neironych", "kie")) == (("neironych", "kie"), None)


@pytest.mark.asyncio
async def test_route_selection_happens_at_create_before_rox_debit(monkeypatch):
    from app.db.models import User, Wallet, Generation
    from app.db.session import SessionFactory
    from app.services.model_catalog import ModelCatalog
    from sqlalchemy import select
    from decimal import Decimal

    async def fake_prepare(_cls, _session, **kwargs):
        params = dict(kwargs["parameters"])
        params["prompt"] = kwargs["prompt"]
        return ModelCatalog.get("kling-4.0"), params, Decimal("20"), 10, Decimal("2")

    async def route(_session, _model, *, user_id=None):
        return ("neironych", "kie"), 10

    class Redis:
        async def eval(self, *args, **kwargs):
            return [1, 60]
        async def rpush(self, *args, **kwargs):
            return 1

    monkeypatch.setattr(GenerationService, "prepare_request", classmethod(fake_prepare))
    monkeypatch.setattr("app.services.generations.configured_route", route)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("1000")))
        await session.commit()
        request = await GenerationService.create(
            session, Redis(), user_id=user.id, model_id="kling-4.0",
            prompt=BASE["prompt"], parameters={**BASE, "keep_original_sound": True},
        )
        assert request.provider == "kie"
        assert request.parameters["_provider_route"] == ["kie"]
        assert request.parameters["_provider_route_revision"] == 10
        assert request.parameters["_provider_route_reason"] == "original_sound"
        assert request.parameters["keep_original_sound"] is True
        row = await session.scalar(select(Generation).where(Generation.id == request.id))
        assert row is not None

    # A route without the capable supplier fails before any Generation row is admitted.
    async def no_kie(_session, _model, *, user_id=None):
        return ("neironych",), 11
    monkeypatch.setattr("app.services.generations.configured_route", no_kie)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("1000")))
        await session.commit()
        before = await session.scalar(select(Wallet.balance).where(Wallet.user_id == user.id))
        with pytest.raises(ValueError, match="KIE"):
            await GenerationService.create(
                session, Redis(), user_id=user.id, model_id="kling-4.0",
                prompt=BASE["prompt"], parameters={**BASE, "keep_original_sound": True},
            )
        after = await session.scalar(select(Wallet.balance).where(Wallet.user_id == user.id))
        assert before == after

@pytest.mark.asyncio
async def test_batch_enqueue_uses_same_capability_route_before_item_debit(monkeypatch):
    from app.db.models import User, Wallet
    from app.db.session import SessionFactory
    from app.services.batch_generation_core import PreparedBatchItem, enqueue_generation
    from app.services.model_catalog import ModelCatalog

    async def route(_session, _model, *, user_id=None):
        return ("neironych", "kie"), 10

    monkeypatch.setattr("app.services.batch_generation_core.configured_route", route)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("1000")))
        await session.commit()
        item = PreparedBatchItem(
            input_url="https://cdn.example/visitor.png",
            spec=ModelCatalog.get("kling-4.0"),
            clean={**BASE, "keep_original_sound": True},
            cost=Decimal("10"),
            billing_seconds=10,
            unit_price=Decimal("1"),
        )
        generation = await enqueue_generation(
            session, user_id=user.id, batch_id=uuid.uuid4(),
            item_id=uuid.uuid4(), ordinal=1, prepared=item, prompt=BASE["prompt"],
        )
        assert generation.provider == "kie"
        assert generation.parameters["_provider_route"] == ["kie"]
        assert generation.parameters["_provider_route_reason"] == "original_sound"


def test_public_model_schema_explains_original_sound_requires_kie():
    from app.services.model_ui import build_model_ui_schema
    from app.services.model_catalog import ModelCatalog
    spec = ModelCatalog.get("kling-4.0")
    schema = build_model_ui_schema({
        "id": spec.id, "known_fields": spec.known_fields,
        "required_fields": spec.required_fields, "price_mode": spec.price_mode,
    })
    field = next(item for item in schema["fields"] if item["name"] == "keep_original_sound")
    assert field["control"] == "toggle"
    assert "KIE" in field["label"]
    assert "Нейроныч" in field["label"]
    for name in ("elements", "voices"):
        other = next(item for item in schema["fields"] if item["name"] == name)
        assert "KIE" in other["label"]
