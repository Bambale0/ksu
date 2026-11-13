"""Kling 4 curated flexible customer photos + administrator-pinned video regression."""
from __future__ import annotations

import pytest

from app.services.trends import TrendRecipeError, TrendService

VIDEO = "https://roxy.example/uploads/refs/video/admin-owned-example.mp4"
IMAGES = [
    "https://roxy.example/uploads/refs/image/visitor-1.jpg",
    "https://roxy.example/uploads/refs/image/visitor-2.jpg",
]


def recipe(*, model: str = "kling-4.0", **overrides):
    return {
        "model_id": model,
        "prompt": "@image_1 and @image_2 follow @video_1",
        "media_type": "video",
        "preview_url": "https://roxy.example/preview.jpg",
        "input_mode": "image",
        "min_references": 2,
        "max_references": 2,
        "parameters": {"duration": 5, "aspect_ratio": "9:16", "resolution": "720p"},
        "template_video_url": VIDEO,
        **overrides,
    }


def test_kling_template_preserves_pinned_video_and_two_user_photo_slots():
    normalized = TrendService.normalize_recipe("Two people", recipe())
    assert normalized["template_video_url"] == VIDEO
    assert normalized["min_references"] == normalized["max_references"] == 2
    assert normalized["video_reference_count"] == 0
    params = TrendService._parameters_with_references(normalized, IMAGES)
    assert params["image_urls"] == IMAGES
    assert params["video_urls"] == [VIDEO]
    assert "template_video_url" not in params


@pytest.mark.parametrize("updates", [
    {"model_id": "kling-4.0-keyframe"},
    {"model_id": "seedance-2.5"},
    {"parameters": {"duration": 5, "resolution": "720p"}},
    {"parameters": {"duration": 5, "aspect_ratio": "auto", "resolution": "720p"}},
    {"parameters": {"duration": 5, "aspect_ratio": "9:16", "video_urls": [VIDEO]}},
])
def test_pinned_template_rejects_invalid_model_or_required_inputs(updates):
    with pytest.raises(TrendRecipeError):
        TrendService.normalize_recipe("Invalid", recipe(**updates))


@pytest.mark.parametrize("count", [0, 1, 3, 8, 10])
def test_pinned_template_accepts_model_supported_image_counts(count):
    # The hidden prompt requires only its indexed slots; additional
    # optional customer photos are allowed up to the actual model capacity.
    urls = [f"https://roxy.example/uploads/refs/image/visitor-{i}.jpg" for i in range(1, count + 1)]
    prompt = "Follow @video_1" + "".join(f" with @image_{i}" for i in range(1, count + 1))
    normalized = TrendService.normalize_recipe("Flexible", recipe(
        prompt=prompt, input_mode="image" if count else "none",
        min_references=count, max_references=count,
    ))
    assert normalized["min_references"] == count
    assert normalized["max_references"] == count
    params = TrendService._parameters_with_references(normalized, urls)
    assert params.get("image_urls", []) == urls
    assert params["video_urls"] == [VIDEO]


def test_pinned_template_infers_missing_image_slots_from_prompt():
    normalized = TrendService.normalize_recipe("Legacy draft", recipe(
        min_references=1, max_references=1,
    ))
    assert normalized["min_references"] == 2
    assert normalized["max_references"] == 2


def test_pinned_template_allows_customer_chosen_optional_photos():
    normalized = TrendService.normalize_recipe("Flexible", recipe(
        prompt="Follow @video_1 with @image_1", min_references=1, max_references=10,
    ))
    assert normalized["min_references"] == 1
    assert normalized["max_references"] == 10
    assert len(TrendService._parameters_with_references(normalized, IMAGES)["image_urls"]) == 2


def test_pinned_template_enforces_real_model_capacity_not_two_photos():
    with pytest.raises(TrendRecipeError, match="не более"):
        TrendService.normalize_recipe("Invalid", recipe(
            prompt="@video_1 with @image_11", min_references=11, max_references=11,
        ))



def test_pinned_kling_photo_max_respects_total_reference_budget():
    from app.services.kling4_contract import Kling4ContractError, normalize_kling4_input

    elements = [
        {"name": f"Person{index}", "image_urls": [
            f"https://roxy.example/element-{index}-a.png",
            f"https://roxy.example/element-{index}-b.png",
        ]}
        for index in range(5)
    ]
    normalized = TrendService.normalize_recipe("Budgeted", recipe(
        parameters={**recipe()["parameters"], "elements": elements},
        min_references=2, max_references=10,
    ))
    # Five named elements + one admin-owned video leave nine of 15 slots.
    assert normalized["min_references"] == 2
    assert normalized["max_references"] == 9

    nine = [f"https://roxy.example/customer-{i}.png" for i in range(1, 10)]
    payload = TrendService._parameters_with_references(normalized, nine)
    assert len(normalize_kling4_input("kling-4.0/reference-to-video", {
        **payload, "prompt": normalized["prompt"]
    })["image_urls"]) == 9
    ten = TrendService._parameters_with_references(normalized, [*nine, "https://roxy.example/customer-10.png"])
    with pytest.raises(Kling4ContractError, match="15 references"):
        normalize_kling4_input("kling-4.0/reference-to-video", {
            **ten, "prompt": normalized["prompt"]
        })


def test_pinned_kling_max_considers_voices_and_rejects_impossible_minimum():
    params = {**recipe()["parameters"], "elements": [{}] * 7, "voices": [{}] * 3}
    normalized = TrendService.normalize_recipe("Budgeted", recipe(
        parameters=params, min_references=2, max_references=10,
    ))
    assert normalized["max_references"] == 4
    with pytest.raises(TrendRecipeError, match="at most 4"):
        TrendService.normalize_recipe("Impossible", recipe(
            parameters=params, min_references=5, max_references=10,
        ))


def test_pinned_video_only_trend_preserves_explicit_zero_photo_policy():
    normalized = TrendService.normalize_recipe("Video only", recipe(
        prompt="Follow @video_1", input_mode="none", min_references=0,
        max_references=0,
    ))
    assert normalized["input_mode"] == "none"
    assert normalized["min_references"] == normalized["max_references"] == 0
    assert TrendService._parameters_with_references(normalized, [])["video_urls"] == [VIDEO]


def test_pinned_template_cannot_change_private_quality_or_ratio():
    normalized = TrendService.normalize_recipe("Locked", recipe())
    with pytest.raises(TrendRecipeError):
        TrendService._parameters_with_references(normalized, IMAGES, aspect_ratio="16:9", require_aspect_ratio=True)
    with pytest.raises(TrendRecipeError):
        TrendService._parameters_with_references(normalized, IMAGES, resolution="1080p", require_aspect_ratio=True)
    assert TrendService._parameters_with_references(normalized, IMAGES, require_aspect_ratio=True)["aspect_ratio"] == "9:16"


def test_non_pinned_kling_remains_user_video_capable_outside_trends():
    normalized = TrendService.normalize_recipe("Normal template", recipe(template_video_url=None))
    assert normalized["template_video_url"] is None
    assert "video_urls" not in TrendService._parameters_with_references(normalized, IMAGES)


@pytest.mark.asyncio
async def test_public_trend_quotes_pinned_video_without_exposing_video_or_extra_controls(monkeypatch):
    from datetime import UTC, datetime
    from decimal import Decimal
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.model_catalog import ModelCatalog

    item = SimpleNamespace(
        id=__import__("uuid").uuid4(), title="Two people", payload=recipe(),
        created_at=datetime.now(UTC), is_active=True,
    )
    session = AsyncMock()
    session.info = {}
    async def prepare(_session, _recipe, **kwargs):
        assert _session.info["authorized_template_video_url"] == VIDEO
        assert kwargs["parameters"]["video_urls"] == [VIDEO]
        return ModelCatalog.get("kling-4.0"), {}, Decimal("300"), 5, Decimal("60")
    monkeypatch.setattr(TrendService, "_prepare_recipe", prepare)
    view = await TrendService.public_view(session, item)
    assert view["reference_requirements"]["image"] == {"min": 2, "max": 2}
    assert view["reference_requirements"]["video"] == {"min": 0, "max": 0}
    assert view["aspect_ratio_options"] == []
    assert "quality_options" not in view
    assert "template_video_url" not in view
    assert VIDEO not in str(view)
    assert view["cost_credits"] == "300.00"
    assert session.info == {}


@pytest.mark.asyncio
async def test_pinned_trend_dispatch_has_server_clip_but_requires_two_photos(monkeypatch):
    import uuid
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.generations import GenerationService

    item = SimpleNamespace(
        id=uuid.uuid4(), title="Two people", payload=recipe(),
        created_at=datetime.now(UTC), is_active=True,
    )
    session = AsyncMock()
    session.info = {}
    session.get = AsyncMock(return_value=item)
    session.scalar = AsyncMock(return_value=item)
    session.commit = AsyncMock()
    generation = SimpleNamespace(id=uuid.uuid4())
    async def create(_session, _redis, **kwargs):
        assert _session.info["authorized_template_video_url"] == VIDEO
        assert kwargs["action_type"] == "trend"
        assert kwargs["parameters"]["image_urls"] == IMAGES
        assert kwargs["parameters"]["video_urls"] == [VIDEO]
        return generation
    monkeypatch.setattr(GenerationService, "create", create)
    result, _ = await TrendService.run(
        session, AsyncMock(), user_id=uuid.uuid4(), trend_id=item.id,
        reference_urls=IMAGES,
    )
    assert result is generation
    assert session.info == {}
    with pytest.raises(TrendRecipeError, match="reference images"):
        await TrendService.run(
            session, AsyncMock(), user_id=uuid.uuid4(), trend_id=item.id,
            reference_urls=IMAGES[:1],
        )
    with pytest.raises(TrendRecipeError, match="video references"):
        await TrendService.run(
            session, AsyncMock(), user_id=uuid.uuid4(), trend_id=item.id,
            reference_urls=IMAGES, video_reference_urls=[VIDEO],
        )


@pytest.mark.asyncio
async def test_server_owned_video_cannot_be_used_in_ordinary_kling_generation(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.kling4_contract import validate_kling4_media
    from app.services.model_catalog import InvalidModelParametersError
    from app.services.template_video import TemplateVideoService

    session = AsyncMock()
    session.info = {}
    good = SimpleNamespace(duration_ms=4500)
    verified = AsyncMock(return_value=good)
    monkeypatch.setattr(TemplateVideoService, "verified", verified)
    payload = {"video_urls": [VIDEO]}

    with pytest.raises(InvalidModelParametersError, match="authenticated upload owner"):
        await validate_kling4_media(session, payload)
    assert verified.await_count == 0

    with TemplateVideoService.authorized(session, VIDEO):
        await validate_kling4_media(session, payload)
    assert verified.await_count == 1
    assert session.info == {}


@pytest.mark.asyncio
async def test_pinned_video_must_be_verified_and_product_owned(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.template_video import TemplateVideoService
    from app.services.reference_static import ReferenceStaticStorage

    row = SimpleNamespace(
        source_url=VIDEO, status="ready", probe_status="ready",
        content_type="video/mp4", size_bytes=1024, duration_ms=4500,
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=row)
    monkeypatch.setattr(ReferenceStaticStorage, "local_url_exists", lambda _: True)
    assert await TemplateVideoService.verified(session, VIDEO) is row
    row.status = "deleted"
    with pytest.raises(ValueError, match="Template video"):
        await TemplateVideoService.verified(session, VIDEO)
    row.status = "ready"
    row.size_bytes = 100 * 1024 * 1024
    assert await TemplateVideoService.verified(session, VIDEO) is row
    row.size_bytes = 101 * 1024 * 1024
    with pytest.raises(ValueError, match="100 MB"):
        await TemplateVideoService.verified(session, VIDEO)
