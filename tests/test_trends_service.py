from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.generations import GenerationService
from app.services.trends import TrendService


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
