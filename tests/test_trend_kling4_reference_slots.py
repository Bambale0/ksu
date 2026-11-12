"""Regression for Kling 4.0 two-photo trends and unsupported reference gaps."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.generations import GenerationService
from app.services.trends import TrendRecipeError, TrendService


def _recipe(prompt: str, **changes):
    payload = {
        "description": "Первое фото поёт, второе слушает.",
        "model_id": "kling-4.0",
        "media_type": "video",
        "prompt": prompt,
        "preview_url": "https://cdn.example/preview.mp4",
        "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "9:16"},
        "input_mode": "none",
        "min_references": 0,
        "max_references": 0,
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize("prompt", [
    "@image_1 sings while @image_2 listens",
    "@Image1 sings while @Image2 listens",
    "@image_1 dances with @IMAGE_2",
])
def test_kling_two_images_inferred_even_if_admin_forgets_image_slots(prompt):
    source = _recipe(prompt)
    before = deepcopy(source)
    recipe = TrendService.normalize_recipe("МОИ СЛЕЗЫ", source)
    assert recipe["input_mode"] == "image"
    assert recipe["min_references"] == 2
    assert recipe["max_references"] == 2
    assert source == before


def test_two_images_raise_both_explicitly_misconfigured_bounds():
    recipe = TrendService.normalize_recipe("МОИ СЛЕЗЫ", _recipe(
        "@image_1 sings. @image_2 listens.",
        input_mode="image", min_references=1, max_references=1,
    ))
    assert (recipe["min_references"], recipe["max_references"]) == (2, 2)


def test_malformed_high_index_rejected_without_silent_clamp():
    with pytest.raises(TrendRecipeError, match="не более|at most"):
        TrendService.normalize_recipe("Trend", _recipe("@image_9 watches"))


def test_other_models_keep_existing_reference_policy():
    recipe = TrendService.normalize_recipe("Фото", {
        **_recipe("@image_1 sings. @image_2 listens."),
        "model_id": "nano-banana-pro", "media_type": "image",
    })
    assert recipe["input_mode"] == "none"
    assert recipe["min_references"] == 0


@pytest.mark.asyncio
async def test_two_image_template_preflight_declares_both_references(monkeypatch):
    captured = {}
    async def fake_preflight(_session, **kwargs):
        captured.update(kwargs)
        assert len(kwargs["parameters"]["image_urls"]) == 2
        assert kwargs["parameters"]["duration"] == 5
        return (SimpleNamespace(id="kling-4.0"), {}, Decimal("100"), 5, Decimal("20"))
    monkeypatch.setattr(GenerationService, "prepare_template_request", fake_preflight)
    recipe = await TrendService.validate_recipe(
        AsyncMock(), title="МОИ СЛЕЗЫ",
        payload=_recipe("@image_1 sings and @image_2 listens"),
    )
    assert recipe["min_references"] == recipe["max_references"] == 2
    assert captured["model_id"] == "kling-4.0"


@pytest.mark.asyncio
async def test_admin_create_replays_same_id_after_lost_gateway_response():
    """Same explicit key returns one persisted trend, not a conflict or duplicate."""
    import uuid

    from starlette.requests import Request
    from sqlalchemy import select
    from app.api.v1 import trends as trends_api
    from app.db.admin_models import AdminTrend
    from app.db.models import AdminAccount, User
    from app.db.session import SessionFactory

    key = "retry-after-502:" + uuid.uuid4().hex
    request = Request({"type": "http", "headers": []})
    payload = trends_api.InlineTrendWriteRequest(
        title="МОИ СЛЕЗЫ",
        payload=_recipe("@image_1 sings while @image_2 listens"),
    )
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add(user)
        await session.flush()
        session.add(AdminAccount(user_id=user.id, role="admin", is_active=True))
        await session.commit()

        first = await trends_api.inline_admin_trend_create(
            payload, request, user, session, idempotency_key=key,
        )
        repeated = await trends_api.inline_admin_trend_create(
            payload, request, user, session, idempotency_key=key,
        )
        assert first["id"] == repeated["id"]
        assert first["idempotency_replayed"] is False
        assert repeated["idempotency_replayed"] is True
        rows = list((await session.scalars(
            select(AdminTrend).where(AdminTrend.id == uuid.UUID(first["id"]))
        )).all())
        assert len(rows) == 1
        assert rows[0].payload["min_references"] == 2
        assert rows[0].payload["max_references"] == 2
