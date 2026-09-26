from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import trends as trends_api
from app.services.billing_access import BillingDecision
from app.services.generations import GenerationService
from app.services.model_routing import resolve_model_request
from app.services.trends import TrendRecipeError, TrendService


def _item() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Editorial",
        is_active=True,
        created_at=now,
        updated_at=now,
        payload={
            "description": "Portrait template",
            "model_id": "nano-banana-pro",
            "prompt": "curated template text",
            "preview_url": "https://cdn.example.invalid/trend.jpg",
            "media_type": "image",
            "input_mode": "image",
            "min_references": 1,
            "max_references": 4,
            "parameters": {
                "aspect_ratio": "1:1",
                "resolution": "1K",
                "output_format": "png",
            },
            "usage_count": 3,
            "sort_order": 5,
            "tags": ["portrait"],
        },
    )


def _generation() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status="queued",
        cost_rox=Decimal("20.00"),
        result_url=None,
    )


def _video_item() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Seedance repeat",
        is_active=True,
        created_at=now,
        updated_at=now,
        payload={
            "description": "Video template",
            "model_id": "seedance-2.0",
            "prompt": "curated video template",
            "preview_url": "https://cdn.example.invalid/trend.mp4",
            "media_type": "video",
            "input_mode": "none",
            "billing_seconds": 10,
            "parameters": {
                "aspect_ratio": "adaptive",
                "resolution": "720p",
                "duration": 10,
            },
        },
    )


def test_normalize_recipe_maps_billing_seconds_to_required_provider_duration() -> None:
    recipe = TrendService.normalize_recipe(
        "Video trend",
        {
            "description": "Seedance template",
            "model_id": "seedance-2.0",
            "prompt": "curated video template",
            "preview_url": "https://cdn.example.invalid/trend.mp4",
            "media_type": "video",
            "input_mode": "none",
            "billing_seconds": 5,
            "parameters": {
                "aspect_ratio": "adaptive",
                "resolution": "720p",
            },
        },
    )

    assert recipe["billing_seconds"] == 5
    assert recipe["parameters"]["duration"] == 5


@pytest.mark.asyncio
async def test_video_public_view_exposes_quality_options_from_resolution_pricing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _video_item()

    async def prepare(_session, *, model_id, prompt, parameters, billing_seconds):  # type: ignore[no-untyped-def]
        prices = {"480p": Decimal("400.00"), "720p": Decimal("500.00"), "1080p": Decimal("600.00")}
        spec = SimpleNamespace(id=model_id, title="Seedance 2.0", family="seedance")
        return spec, parameters, prices[parameters["resolution"]], billing_seconds, Decimal("50.00")

    monkeypatch.setattr(GenerationService, "prepare_request", prepare)

    view = await TrendService.public_view(AsyncMock(), item)

    assert view["cost_credits"] == "500.00"
    assert view["quality_options"] == [
        {
            "value": "480p",
            "label": "480p",
            "cost_credits": "400.00",
            "cost_rox": "400.00",
            "cost_rub": "400.00",
            "billing_seconds": 10,
            "default": False,
        },
        {
            "value": "720p",
            "label": "720p",
            "cost_credits": "500.00",
            "cost_rox": "500.00",
            "cost_rub": "500.00",
            "billing_seconds": 10,
            "default": True,
        },
        {
            "value": "1080p",
            "label": "1080p",
            "cost_credits": "600.00",
            "cost_rox": "600.00",
            "cost_rub": "600.00",
            "billing_seconds": 10,
            "default": False,
        },
    ]


@pytest.mark.asyncio
async def test_video_public_view_preserves_recipe_resolution_absent_from_suggestions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _video_item()
    item.payload["parameters"]["resolution"] = "4K"

    async def prepare(_session, *, model_id, prompt, parameters, billing_seconds):  # type: ignore[no-untyped-def]
        prices = {"4K": Decimal("900.00"), "480p": Decimal("400.00"), "720p": Decimal("500.00"), "1080p": Decimal("600.00")}
        spec = SimpleNamespace(id=model_id, title="Seedance 2.0", family="seedance")
        return spec, parameters, prices[parameters["resolution"]], billing_seconds, Decimal("90.00")

    monkeypatch.setattr(GenerationService, "prepare_request", prepare)

    view = await TrendService.public_view(AsyncMock(), item)

    assert view["cost_credits"] == "900.00"
    assert [option["value"] for option in view["quality_options"]] == ["4K", "480p", "720p", "1080p"]
    assert view["quality_options"][0]["default"] is True


@pytest.mark.asyncio
async def test_customer_price_reuses_billing_decision_for_quality_options(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    async def decision(_session, *, user_id, retail_cost):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return BillingDecision(
            retail_cost=Decimal(str(retail_cost)),
            effective_cost=Decimal("0.00"),
            admin_free=True,
        )

    monkeypatch.setattr(trends_api.BillingAccessService, "decision", decision)
    view = await trends_api._customer_price(
        AsyncMock(),
        user_id=uuid.uuid4(),
        item={
            "cost_credits": "500.00",
            "quality_options": [
                {"value": "480p", "cost_credits": "400.00"},
                {"value": "720p", "cost_credits": "500.00"},
                {"value": "1080p", "cost_credits": "600.00"},
            ],
        },
    )

    assert calls == 1
    assert view["admin_free"] is True
    assert view["cost_rox"] == "0.00"
    assert [option["cost_rox"] for option in view["quality_options"]] == ["0.00", "0.00", "0.00"]
    assert [option["retail_cost_rox"] for option in view["quality_options"]] == ["400.00", "500.00", "600.00"]


@pytest.mark.asyncio
async def test_public_view_does_not_serialize_curated_prompt_or_settings() -> None:
    item = _item()
    session = AsyncMock()
    view = await TrendService.public_view(session, item)
    assert view["prompt_hidden"] is True
    assert view["prompt_actions_allowed"] is False
    assert "prompt" not in view
    assert "parameters" not in view
    assert "curated template text" not in repr(view)
    assert view["model"]["id"] == "nano-banana-pro"


@pytest.mark.asyncio
async def test_run_uses_server_owned_recipe_and_only_merges_reference_urls(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _item()
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    generation = _generation()
    create = AsyncMock(return_value=generation)
    monkeypatch.setattr(GenerationService, "create", create)

    user_id = uuid.uuid4()
    reference = "https://cdn.example.invalid/user-reference.jpg"
    returned, meta = await TrendService.run(
        session,
        AsyncMock(),
        user_id=user_id,
        trend_id=item.id,
        reference_urls=[reference],
    )

    assert returned is generation
    kwargs = create.await_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["model_id"] == "nano-banana-pro"
    assert kwargs["prompt"] == "curated template text"
    assert kwargs["parameters"]["aspect_ratio"] == "1:1"
    assert kwargs["parameters"]["image_input"] == [reference]
    assert kwargs["action_type"] == "trend"
    assert meta["prompt_hidden"] is True
    assert item.payload["usage_count"] == 4
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_applies_validated_video_resolution_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _video_item()
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    create = AsyncMock(return_value=_generation())
    monkeypatch.setattr(GenerationService, "create", create)

    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=[],
        resolution="480p",
    )

    assert create.await_args.kwargs["parameters"]["resolution"] == "480p"
    assert create.await_args.kwargs["parameters"]["duration"] == 10

    with pytest.raises(TrendRecipeError, match="Unsupported video quality"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            resolution="4K",
        )


@pytest.mark.asyncio
async def test_usage_counter_failure_does_not_fail_created_generation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _item()
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.side_effect = RuntimeError("analytics unavailable")
    generation = _generation()
    monkeypatch.setattr(GenerationService, "create", AsyncMock(return_value=generation))

    returned, meta = await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=["https://cdn.example.invalid/reference.jpg"],
    )

    assert returned is generation
    assert meta["prompt_hidden"] is True
    session.rollback.assert_awaited_once()



def test_normalize_recipe_uses_admin_selected_names_and_infers_field_types() -> None:
    recipe = TrendService.normalize_recipe("Birthday", {
        "model_id": "nano-banana-pro", "prompt": "Birthday portrait with festive typography",
        "preview_url": "https://cdn.example.invalid/birthday.jpg", "media_type": "image",
        "input_mode": "image", "min_references": 1, "max_references": 1,
        "parameters": {"aspect_ratio": "1:1", "resolution": "1K", "output_format": "png"},
        "user_fields": [
            {"key": "Возраст", "label": "Возраст", "type": "text", "min": 1, "max": 120, "default_value": "28"},
            {"key": "Имя", "label": "Имя", "type": "number"},
            {"key": "Дата", "label": "Дата"},
        ],
    })
    assert recipe["user_fields"] == [
        {"key": "Возраст", "label": "Возраст", "type": "number", "required": True, "max_length": 160},
        {"key": "Имя", "label": "Имя", "type": "text", "required": True, "max_length": 160},
        {"key": "Дата", "label": "Дата", "type": "date", "required": True, "max_length": 160},
    ]


def test_normalize_recipe_keeps_legacy_prompt_tokens_working() -> None:
    recipe = TrendService.normalize_recipe("Legacy", {
        "model_id": "nano-banana-pro", "prompt": "Happy birthday {{Возраст}}, {{Имя}}!",
        "preview_url": "https://cdn.example.invalid/x.jpg", "media_type": "image",
        "input_mode": "image", "min_references": 1, "max_references": 1,
        "parameters": {"aspect_ratio": "1:1", "resolution": "1K", "output_format": "png"},
    })
    assert [field["key"] for field in recipe["user_fields"]] == ["Возраст", "Имя"]
    assert recipe["user_fields"][0]["type"] == "number"
    assert recipe["user_fields"][1]["type"] == "text"


@pytest.mark.asyncio
async def test_run_applies_admin_selected_values_as_server_side_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _item()
    item.payload["prompt"] = "Birthday portrait with a cake and text from the original recipe"
    item.payload["user_fields"] = [
        {"key": "Возраст", "label": "Возраст", "type": "text"},
        {"key": "Надпись", "label": "Надпись", "type": "number"},
    ]
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    generation = _generation()
    create = AsyncMock(return_value=generation)
    monkeypatch.setattr(GenerationService, "create", create)

    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=["https://cdn.example.invalid/user.jpg"],
        user_values={"Возраст": "31", "Надпись": "С юбилеем!"},
    )
    rendered = create.await_args.kwargs["prompt"]
    assert rendered.startswith("Birthday portrait with a cake and text from the original recipe")
    assert "- Возраст: 31" in rendered
    assert "- Надпись: С юбилеем!" in rendered
    assert "имеют приоритет" in rendered
    assert "{{" not in rendered

    with pytest.raises(TrendRecipeError, match="лишние"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=["https://cdn.example.invalid/user.jpg"],
            user_values={"Возраст": "31", "Надпись": "С юбилеем!", "prompt": "steal"},
        )


@pytest.mark.asyncio
async def test_run_validates_auto_number_without_admin_ranges(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _item()
    item.payload["prompt"] = "Birthday portrait"
    item.payload["user_fields"] = [{"key": "Возраст", "label": "Возраст", "min": 1, "max": 120}]
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    create = AsyncMock(return_value=_generation())
    monkeypatch.setattr(GenerationService, "create", create)

    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=["https://cdn.example.invalid/user.jpg"],
        user_values={"Возраст": "121"},
    )
    assert "- Возраст: 121" in create.await_args.kwargs["prompt"]

    with pytest.raises(TrendRecipeError, match="должно быть числом"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=["https://cdn.example.invalid/user.jpg"],
            user_values={"Возраст": "тридцать"},
        )


@pytest.mark.asyncio
async def test_run_substitutes_legacy_tokens_and_keeps_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _item()
    item.payload["prompt"] = "На торте должно быть {{Возраст}} свечей, подпись {{Имя}}"
    item.payload.pop("user_fields", None)
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    create = AsyncMock(return_value=_generation())
    monkeypatch.setattr(GenerationService, "create", create)

    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=["https://cdn.example.invalid/user.jpg"],
        user_values={"Возраст": "31", "Имя": "Игорь"},
    )
    rendered = create.await_args.kwargs["prompt"]
    assert "На торте должно быть 31 свечей, подпись Игорь" in rendered
    assert "- Возраст: 31" in rendered
    assert "- Имя: Игорь" in rendered


@pytest.mark.asyncio
async def test_public_view_exposes_safe_empty_field_schema_not_hidden_prompt_or_defaults() -> None:
    item = _item()
    item.payload["prompt"] = "Birthday portrait"
    item.payload["user_fields"] = [
        {"key": "Возраст", "label": "Возраст", "type": "text", "min": 1, "max": 120, "default_value": "28"}
    ]
    view = await TrendService.public_view(AsyncMock(), item)
    assert view["user_fields"] == [
        {"key": "Возраст", "label": "Возраст", "type": "number", "required": True, "max_length": 160}
    ]
    assert "prompt" not in view and "Birthday portrait" not in repr(view)
    assert "default_value" not in repr(view["user_fields"])
    assert "min" not in view["user_fields"][0] and "max" not in view["user_fields"][0]


def test_seedance_trend_infers_required_user_images_from_typed_prompt() -> None:
    recipe = TrendService.normalize_recipe(
        "Dance replacement",
        {
            "description": "Image1 dancer, Image2 filmer, Image3 car person",
            "model_id": "seedance-2.0",
            "prompt": "@Image1 dances, @Image2 films, @Image3 exits the car, follow @Video1",
            "preview_url": "https://cdn.example.invalid/original.mp4",
            "media_type": "video",
            "input_mode": "none",
            "billing_seconds": 5,
            "parameters": {
                "aspect_ratio": "adaptive",
                "resolution": "720p",
                "duration": 5,
            },
        },
    )

    assert recipe["input_mode"] == "image"
    assert recipe["min_references"] == 3
    assert recipe["max_references"] >= 3


@pytest.mark.asyncio
async def test_seedance_trend_validation_binds_video_preview_to_video1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    prepare = AsyncMock(
        return_value=(
            SimpleNamespace(id="seedance-2.0"),
            {},
            Decimal("250.00"),
            5,
            Decimal("50.00"),
        )
    )
    monkeypatch.setattr(GenerationService, "prepare_request", prepare)

    recipe = await TrendService.validate_recipe(
        AsyncMock(),
        title="Dance replacement",
        payload={
            "description": "Three people from user photos",
            "model_id": "seedance-2.0",
            "prompt": "@Image1 dances, @Image2 films, @Image3 exits the car, follow @Video1",
            "preview_url": "https://cdn.example.invalid/original.mp4",
            "media_type": "video",
            "input_mode": "none",
            "billing_seconds": 5,
            "parameters": {
                "aspect_ratio": "adaptive",
                "resolution": "720p",
                "duration": 5,
            },
        },
    )

    kwargs = prepare.await_args.kwargs
    assert recipe["min_references"] == 3
    assert kwargs["parameters"]["reference_image_urls"] == [
        "https://example.invalid/trend-reference-1.jpg",
        "https://example.invalid/trend-reference-2.jpg",
        "https://example.invalid/trend-reference-3.jpg",
    ]
    assert kwargs["parameters"]["reference_video_urls"] == [
        "https://cdn.example.invalid/original.mp4"
    ]


@pytest.mark.asyncio
async def test_seedance_trend_run_keeps_user_images_and_server_video_preview(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _video_item()
    item.payload.update(
        {
            "prompt": "@Image1 dances, @Image2 films, @Image3 exits the car, follow @Video1",
            "preview_url": "https://cdn.example.invalid/original.mp4",
            "input_mode": "none",
            "min_references": 0,
            "max_references": 0,
        }
    )
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    create = AsyncMock(return_value=_generation())
    monkeypatch.setattr(GenerationService, "create", create)

    refs = [
        "https://cdn.example.invalid/person-1.jpg",
        "https://cdn.example.invalid/person-2.jpg",
        "https://cdn.example.invalid/person-3.jpg",
    ]
    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=refs,
    )

    parameters = create.await_args.kwargs["parameters"]
    assert parameters["reference_image_urls"] == refs
    assert parameters["reference_video_urls"] == [
        "https://cdn.example.invalid/original.mp4"
    ]


def test_trend_validation_reference_placeholders_are_unique() -> None:
    refs = TrendService._validation_reference_urls(3)

    assert refs == [
        "https://example.invalid/trend-reference-1.jpg",
        "https://example.invalid/trend-reference-2.jpg",
        "https://example.invalid/trend-reference-3.jpg",
    ]
    assert len(set(refs)) == 3


def test_seedance_trend_validation_refs_survive_router_without_deduplication() -> None:
    recipe = TrendService.normalize_recipe(
        "Dance replacement",
        {
            "description": "Three people and one source video",
            "model_id": "seedance-2.0",
            "prompt": "@Image1 dances, @Image2 films, @Image3 exits the car, follow @Video1",
            "preview_url": "https://cdn.example.invalid/original.mp4",
            "media_type": "video",
            "billing_seconds": 5,
            "parameters": {
                "aspect_ratio": "adaptive",
                "resolution": "720p",
                "duration": 5,
            },
        },
    )
    refs = TrendService._validation_reference_urls(recipe["min_references"])
    parameters = TrendService._parameters_with_references(recipe, refs)

    routed = resolve_model_request(recipe["model_id"], parameters)

    assert routed.parameters["reference_image_urls"] == refs
    assert len(routed.parameters["reference_image_urls"]) == 3
    assert routed.parameters["reference_video_urls"] == [
        "https://cdn.example.invalid/original.mp4"
    ]


@pytest.mark.asyncio
async def test_seedance_trend_run_binds_video_preview_without_explicit_video_alias(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    item = _video_item()
    item.payload.update(
        {
            "prompt": "@Image1 holds the same birthday cake and candles as the reference scene",
            "preview_url": "https://cdn.example.invalid/original.mp4",
            "input_mode": "image",
            "min_references": 1,
            "max_references": 1,
        }
    )
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = item
    create = AsyncMock(return_value=_generation())
    monkeypatch.setattr(GenerationService, "create", create)

    reference = "https://cdn.example.invalid/person.jpg"
    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=[reference],
    )

    parameters = create.await_args.kwargs["parameters"]
    assert parameters["reference_image_urls"] == [reference]
    assert parameters["reference_video_urls"] == [
        "https://cdn.example.invalid/original.mp4"
    ]
