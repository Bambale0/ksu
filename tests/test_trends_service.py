from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.generations import GenerationService
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
