from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1.ai_reference import AiReferenceRequest, _build as build_ai_reference
from app.api.v1.feed_remix import RemixCompositionRequest
from app.api.v1.pinterest_repeat import (
    PinterestRepeatRequest,
    _build as build_pinterest_repeat,
    _generation_matches_recipe,
    router as pinterest_router,
)
from app.db.models import Generation
from app.services.ai_reference import AiReferenceError, AiReferenceService
from app.services.feed_remix import FeedRemixReferenceError, FeedRemixService
from app.services.pinterest_repeat import PinterestRepeatError, PinterestRepeatService


def _pinterest_request(**overrides):  # type: ignore[no-untyped-def]
    return PinterestRepeatService.build_request(
        scene_reference_url="https://cdn.example.test/scene.jpg",
        identity_reference_urls=["https://cdn.example.test/person.jpg"],
        height_cm=170,
        weight_kg=70,
        confirmed=True,
        **overrides,
    )


@pytest.mark.parametrize("scenario", ["hd", "edit"])
def test_reference_recipe_keeps_the_selected_frame(scenario: str) -> None:
    recipe = AiReferenceService.build_request(
        scenario=scenario,
        reference_urls=["https://cdn.example.test/person.jpg"],
        instruction="Change the jacket",
        aspect_ratio="9:16",
    )
    assert recipe.parameters["aspect_ratio"] == "9:16"


@pytest.mark.parametrize("scenario", ["hd", "edit"])
@pytest.mark.parametrize("aspect_ratio", [None, "auto", " AUTO ", "2:7", "", "   "])
def test_reference_recipe_requires_a_real_frame(scenario: str, aspect_ratio: str | None) -> None:
    with pytest.raises(AiReferenceError, match="формат|[Aa]spect ratio"):
        AiReferenceService.build_request(
            scenario=scenario,
            reference_urls=["https://cdn.example.test/person.jpg"],
            instruction="Change the jacket",
            aspect_ratio=aspect_ratio,
        )


def test_pinterest_recipe_keeps_frame_in_idempotency_identity() -> None:
    recipe = _pinterest_request(aspect_ratio="9:16")
    stored = SimpleNamespace(
        prompt=recipe.prompt,
        parameters={"_requested_model_id": recipe.model_id, **recipe.parameters},
    )
    assert recipe.parameters["aspect_ratio"] == "9:16"
    assert _generation_matches_recipe(stored, _pinterest_request(aspect_ratio="9:16"))
    assert not _generation_matches_recipe(stored, _pinterest_request(aspect_ratio="16:9"))


@pytest.mark.parametrize("aspect_ratio", [None, "auto", " AUTO ", "2:7", "", "   "])
def test_pinterest_recipe_requires_a_real_frame(aspect_ratio: str | None) -> None:
    with pytest.raises(PinterestRepeatError, match="формат|[Aa]spect ratio"):
        _pinterest_request(aspect_ratio=aspect_ratio)


def test_special_request_dtos_preserve_selected_frame() -> None:
    ai = AiReferenceRequest(
        scenario="hd", reference_urls=["https://cdn.example.test/person.jpg"], aspect_ratio="9:16",
    )
    pinterest = PinterestRepeatRequest(
        scene_reference_url="https://cdn.example.test/scene.jpg",
        identity_reference_urls=["https://cdn.example.test/person.jpg"],
        height_cm=170, weight_kg=70, aspect_ratio="9:16",
    )
    remix = RemixCompositionRequest(aspect_ratio="9:16")
    assert ai.model_dump()["aspect_ratio"] == "9:16"
    assert pinterest.model_dump()["aspect_ratio"] == "9:16"
    assert remix.model_dump()["aspect_ratio"] == "9:16"
    assert build_ai_reference(ai).parameters["aspect_ratio"] == "9:16"
    assert build_pinterest_repeat(pinterest, confirmed=True).parameters["aspect_ratio"] == "9:16"


def test_pinterest_options_route_is_registered() -> None:
    routes = {(route.path, frozenset(route.methods or set())) for route in pinterest_router.routes}
    assert ("/pinterest-repeat/options", frozenset({"GET"})) in routes


def test_special_options_describe_real_frames_and_preserve_create_defaults() -> None:
    portrait = AiReferenceService.options(scenario="create", subject="adult")
    pet = AiReferenceService.options(scenario="create", subject="pet")
    hd = AiReferenceService.options(scenario="hd")
    pinterest = PinterestRepeatService.options()
    assert portrait["default_aspect_ratio"] == "3:4"
    assert pet["default_aspect_ratio"] == "1:1"
    assert hd["default_aspect_ratio"] is None
    assert hd["aspect_ratio_required"] is True
    assert pinterest["default_aspect_ratio"] is None
    assert pinterest["aspect_ratio_required"] is True
    for options in (portrait, pet, hd, pinterest):
        assert "auto" not in options["aspect_ratio_options"]
        assert "9:16" in options["aspect_ratio_options"]


def _source_with_auto() -> Generation:
    return Generation(
        id=uuid.uuid4(), user_id=uuid.uuid4(), kind="text_to_image", status="succeeded",
        prompt="Hidden author prompt", parameters={
            "_model_id": "nano-banana-pro", "_requested_model_id": "nano-banana-pro",
            "aspect_ratio": "auto", "resolution": "2K",
        },
        source_feed_gen_id=None, input_url=None, feed_prompt_visible=False,
    )


async def _stub_source(monkeypatch, source: Generation, owned_references=None) -> None:  # type: ignore[no-untyped-def]
    async def visible(_session, _source_id, *, surface):
        return source

    async def card(_session, _source, *, viewer_user_id, surface):
        return {"prompt_hidden": True, "preview_url": "/media/preview.jpg"}

    async def references(_session, *, user_id, reference_ids):
        return owned_references or []

    monkeypatch.setattr("app.services.feed_remix.FeedService.assert_surface_visible", visible)
    monkeypatch.setattr("app.services.feed_remix.FeedService.to_card", card)
    monkeypatch.setattr("app.services.feed_remix.ReferenceService.resolve_owned", references)


async def test_remix_prepare_removes_old_auto_and_requests_an_explicit_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_auto()
    await _stub_source(monkeypatch, source)
    prepared = await FeedRemixService.prepare(
        object(), source_generation_id=source.id, viewer_user_id=uuid.uuid4(), surface="feed",
    )
    assert "aspect_ratio" not in prepared["settings"]
    assert prepared["default_aspect_ratio"] is None
    assert prepared["aspect_ratio_required"] is True
    assert "9:16" in prepared["aspect_ratio_options"]
    assert "auto" not in prepared["aspect_ratio_options"]
    assert prepared["prompt"] == ""
    assert source.parameters["aspect_ratio"] == "auto"  # History is immutable.


@pytest.mark.parametrize("aspect_ratio", [None, "", "   "])
async def test_remix_quote_does_not_silently_square_an_old_auto_recipe(monkeypatch, aspect_ratio) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_auto()
    await _stub_source(monkeypatch, source)
    called = False

    async def forbidden_prepare(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Quote must reject before generation admission")

    monkeypatch.setattr("app.services.feed_remix.GenerationService.prepare_request", forbidden_prepare)
    with pytest.raises(FeedRemixReferenceError, match="формат|aspect_ratio"):
        await FeedRemixService.quote(
            object(), source_generation_id=source.id, remix_author_id=uuid.uuid4(),
            surface="feed", prompt_override=None, reference_ids=[], confirm_own_references=True,
            aspect_ratio=aspect_ratio,
        )
    assert called is False


async def test_remix_quote_preserves_selected_frame_and_hidden_source_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_auto()
    await _stub_source(monkeypatch, source)
    captured = {}

    async def prepare(_session, **kwargs):
        captured.update(kwargs)
        return (
            SimpleNamespace(id=kwargs["model_id"]), kwargs["parameters"],
            Decimal("8.00"), None, Decimal("8.00"),
        )

    async def billing(_session, *, user_id, retail_cost):
        return SimpleNamespace(
            effective_cost=retail_cost, retail_cost=retail_cost, admin_free=False,
        )

    monkeypatch.setattr("app.services.feed_remix.GenerationService.prepare_request", prepare)
    monkeypatch.setattr("app.services.feed_remix.BillingAccessService.decision", billing)
    quote = await FeedRemixService.quote(
        object(), source_generation_id=source.id, remix_author_id=uuid.uuid4(),
        surface="feed", prompt_override="Must not expose or replace the hidden recipe",
        reference_ids=[], confirm_own_references=True, aspect_ratio="9:16",
    )
    assert captured["prompt"] == "Hidden author prompt"
    assert captured["parameters"] == {"aspect_ratio": "9:16", "resolution": "2K"}
    assert quote["cost_rox"] == "8.00"
    assert source.parameters["aspect_ratio"] == "auto"


async def test_remix_prepare_preserves_an_existing_explicit_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_auto()
    source.parameters = {**source.parameters, "aspect_ratio": "16:9"}
    await _stub_source(monkeypatch, source)
    prepared = await FeedRemixService.prepare(
        object(), source_generation_id=source.id, viewer_user_id=uuid.uuid4(), surface="feed",
    )
    assert prepared["settings"]["aspect_ratio"] == "16:9"
    assert prepared["default_aspect_ratio"] == "16:9"


def _source_with_frame(model_id: str) -> Generation:
    source = _source_with_auto()
    source.kind = "image_to_video"
    image_field = "image_urls" if model_id == "kling-3.0" else "first_frame_url"
    image_value = ["https://cdn.example.test/source.jpg"] if image_field == "image_urls" else "https://cdn.example.test/source.jpg"
    source.parameters = {
        "_model_id": model_id, "_requested_model_id": model_id,
        "duration": 5, image_field: image_value,
    }
    return source


@pytest.mark.parametrize("model_id", ["kling-3.0", "wan-2.7-i2v"])
async def test_remix_source_driven_mode_exposes_no_frame_choices_and_rejects_override(
    monkeypatch, model_id: str,
) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_frame(model_id)
    own_image = SimpleNamespace(kind="image", source_url="https://cdn.example.test/own.jpg")
    await _stub_source(monkeypatch, source, [own_image])
    prepared = await FeedRemixService.prepare(
        object(), source_generation_id=source.id, viewer_user_id=uuid.uuid4(), surface="feed",
    )
    assert prepared["aspect_ratio_options"] == []
    assert prepared["aspect_ratio_required"] is False
    assert prepared["default_aspect_ratio"] is None

    async def forbidden_prepare(*args, **kwargs):
        raise AssertionError("Unsupported frame override must fail before admission")

    monkeypatch.setattr("app.services.feed_remix.GenerationService.prepare_request", forbidden_prepare)
    with pytest.raises(FeedRemixReferenceError, match="формат"):
        await FeedRemixService.quote(
            object(), source_generation_id=source.id, remix_author_id=uuid.uuid4(),
            surface="feed", prompt_override=None, reference_ids=[uuid.uuid4()],
            confirm_own_references=True, aspect_ratio="9:16",
        )


async def test_kling_frame_remix_quote_preserves_ratio_omission(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = _source_with_frame("kling-3.0")
    own_image = SimpleNamespace(kind="image", source_url="https://cdn.example.test/own.jpg")
    await _stub_source(monkeypatch, source, [own_image])
    captured = {}

    async def prepare(_session, **kwargs):
        captured.update(kwargs)
        return (
            SimpleNamespace(id=kwargs["model_id"]), kwargs["parameters"],
            Decimal("75.00"), 5, Decimal("15.00"),
        )

    async def billing(_session, *, user_id, retail_cost):
        return SimpleNamespace(
            effective_cost=retail_cost, retail_cost=retail_cost, admin_free=False,
        )

    monkeypatch.setattr("app.services.feed_remix.GenerationService.prepare_request", prepare)
    monkeypatch.setattr("app.services.feed_remix.BillingAccessService.decision", billing)
    quote = await FeedRemixService.quote(
        object(), source_generation_id=source.id, remix_author_id=uuid.uuid4(),
        surface="feed", prompt_override=None, reference_ids=[uuid.uuid4()],
        confirm_own_references=True,
    )
    assert "aspect_ratio" not in captured["parameters"]
    assert captured["parameters"]["reference_images"] == [own_image.source_url]
    assert quote["cost_rox"] == "75.00"
