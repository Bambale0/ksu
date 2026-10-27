"""Owner-scoped workflow recovery and accounting across actual DB/API seams."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.api.deps import get_current_user
from app.api.v1.generations import _generation_view
from app.api.v1.trends import router
from app.core.config import settings
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount, Generation, User, Wallet
from app.db.session import SessionFactory
from app.db.trend_workflow_models import TrendWorkflowRun
from app.services.trend_workflows import TrendWorkflowService


def _recipe() -> dict:
    return {
        "schema_version": 2, "workflow_type": "sequential_photo_video",
        "description": "Original instructions", "preview_url": "https://example.invalid/preview.jpg",
        "steps": [
            {"id": "photo", "kind": "image", "title": "Prepare photo", "instructions": "Your face",
             "model_id": "nano-banana-pro", "prompt": "PRIVATE_STEP_PHOTO",
             "parameters": {"aspect_ratio": "9:16", "resolution": "1K"},
             "inputs": [{"id": "person_photo", "type": "image", "label": "Your photo", "help": "Upload a clear face photo", "required": True, "order": 0}]},
            {"id": "video", "kind": "video", "title": "Animate photo", "instructions": "Check the photo",
             "model_id": "seedance-2.5", "prompt": "PRIVATE_STEP_VIDEO", "inputs": [],
             "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "9:16"},
             "bindings": [{"from": "photo.output_image", "to": "reference_image_urls"}]},
        ],
    }


async def _scenario() -> tuple[User, User, uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % (2**62), first_name="Synthetic owner")
        author = User(telegram_id=uuid.uuid4().int % (2**62), first_name="Synthetic author")
        session.add_all([user, author])
        await session.flush()
        admin = AdminAccount(user_id=author.id, role="admin")
        session.add(admin)
        await session.flush()
        trend = AdminTrend(title="Original title", payload=_recipe(), created_by_admin_id=admin.id)
        session.add_all([trend, Wallet(user_id=user.id, balance=Decimal("10000.00"))])
        await session.commit()
        run = await TrendWorkflowService.create_or_resume(
            session, user_id=user.id, trend_id=trend.id, command_key=str(uuid.uuid4()), request={},
        )
        return user, author, trend.id, run.id


@pytest.mark.asyncio
async def test_opening_workflow_state_does_not_count_as_generation() -> None:
    user, _author, trend_id, run_id = await _scenario()
    async with SessionFactory() as session:
        trend = await session.get(AdminTrend, trend_id)
        run = await session.get(TrendWorkflowRun, run_id)
        assert int(trend.payload.get("usage_count", 0)) == 0
        assert run.usage_incremented is False
        assert run.user_id == user.id


@pytest.mark.asyncio
async def test_run_snapshot_remains_self_contained_when_template_hidden_or_edited() -> None:
    user, _author, trend_id, run_id = await _scenario()
    async with SessionFactory() as session:
        trend = await session.get(AdminTrend, trend_id)
        trend.title = "Changed title"
        trend.payload = {**trend.payload, "description": "Changed instructions"}
        trend.is_active = False
        await session.commit()
    async with SessionFactory() as session:
        view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
    assert view["title"] == "Original title"
    assert view["description"] == "Original instructions"
    assert view["preview_url"] == "https://example.invalid/preview.jpg"
    assert view["steps"][0]["model"]["id"] == "nano-banana-pro"
    assert view["steps"][1]["settings_summary"]["duration"] == 5
    assert "PRIVATE_STEP" not in repr(view)
    assert all("prompt" not in step and "parameters" not in step for step in view["steps"])


@pytest.mark.asyncio
async def test_latest_run_http_is_owner_scoped_even_when_template_hidden() -> None:
    owner, other, trend_id, run_id = await _scenario()
    async with SessionFactory() as session:
        trend = await session.get(AdminTrend, trend_id)
        trend.is_active = False
        await session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    identity = owner

    async def current_user():
        return identity

    app.dependency_overrides[get_current_user] = current_user
    async with AsyncClient(transport=ASGITransport(app), base_url="http://workflow.test") as client:
        response = await client.get(f"/api/v1/trends/{trend_id}/workflow")
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(run_id)
        identity = other
        assert (await client.get(f"/api/v1/trends/{trend_id}/workflow")).status_code == 404
        assert (await client.get(f"/api/v1/trends/workflows/{run_id}")).status_code == 404


@pytest.mark.asyncio
async def test_first_accepted_step_counts_once_and_history_can_resume_without_prompt_leak() -> None:
    user, _author, trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    request = {"image_inputs": [{"slot_id": "person_photo", "url": "https://example.invalid/user.jpg"}], "values": {}}
    try:
        async with SessionFactory() as session:
            quote = await TrendWorkflowService.quote_step(
                session, run_id=run_id, step_key="photo", user_id=user.id, request=request,
            )
            request["quoted_cost_rox"] = quote["cost_rox"]
            step = await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                command_key="accepted-photo", request=request,
            )
            generation = await session.get(Generation, step.generation_id)
            view = _generation_view(generation)
            assert view["trend_workflow"] == {"id": str(run_id), "trend_id": str(trend_id), "step_id": "photo"}
            assert view["prompt"] == "" and view["settings"] == {}
            assert "PRIVATE_STEP" not in repr(view)
            assert int((await session.get(AdminTrend, trend_id)).payload["usage_count"]) == 1
        async with SessionFactory() as session:
            replay = await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                command_key="accepted-photo", request=request,
            )
            assert str(replay.generation_id) == view["id"]
            assert int((await session.get(AdminTrend, trend_id)).payload["usage_count"]) == 1
    finally:
        await redis.aclose()


def test_seedance_video_prompt_can_reference_the_bound_prepared_image() -> None:
    recipe = _recipe()
    recipe["steps"][1]["prompt"] = "Animate @Image1, preserve the prepared text and clothing"
    normalized = TrendWorkflowService.normalize_recipe("Seedance photo animation", recipe)
    assert normalized["steps"][1]["bindings"][0]["to"] == "reference_image_urls"


def test_seedance_video_prompt_rejects_an_unbound_second_image() -> None:
    recipe = _recipe()
    recipe["steps"][1]["prompt"] = "Animate @Image1 and @Image2"
    with pytest.raises(ValueError):
        TrendWorkflowService.normalize_recipe("Invalid extra input", recipe)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_parallel_step_requests_have_one_generation_debit_and_outbox(same_key: bool) -> None:
    import asyncio
    from sqlalchemy import func, select
    from app.db.models import WalletTransaction
    from app.db.reliability_models import GenerationOutbox

    user, _author, trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    request = {"image_inputs": [{"slot_id": "person_photo", "url": "https://example.invalid/user.jpg"}], "values": {}}
    async with SessionFactory() as session:
        quote = await TrendWorkflowService.quote_step(
            session, run_id=run_id, step_key="photo", user_id=user.id, request=request,
        )
        request["quoted_cost_rox"] = quote["cost_rox"]

    async def submit(key: str):
        async with SessionFactory() as session:
            step = await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                command_key=key, request=dict(request),
            )
            return step.generation_id

    try:
        results = await asyncio.wait_for(
            asyncio.gather(submit("parallel-a"), submit("parallel-a" if same_key else "parallel-b")), 15,
        )
        assert results[0] == results[1]
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user.id)) == 1
            assert await session.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) == 1
            assert await session.scalar(select(func.count()).select_from(GenerationOutbox).where(GenerationOutbox.generation_id == results[0])) == 1
            assert (await session.get(Wallet, user.id)).balance == Decimal("10000.00") - Decimal(quote["cost_rox"])
            assert (await session.get(AdminTrend, trend_id)).payload["usage_count"] == 1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_stale_quote_rolls_back_generation_wallet_outbox_usage_and_attempt() -> None:
    from sqlalchemy import func, select
    from app.db.models import WalletTransaction
    from app.db.trend_workflow_models import TrendWorkflowStep

    user, _author, trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    request = {"image_inputs": [{"slot_id": "person_photo", "url": "https://example.invalid/user.jpg"}], "values": {}}
    try:
        async with SessionFactory() as session:
            quote = await TrendWorkflowService.quote_step(
                session, run_id=run_id, step_key="photo", user_id=user.id, request=request,
            )
            request["quoted_cost_rox"] = str(Decimal(quote["cost_rox"]) + Decimal("1.00"))
            with pytest.raises(ValueError, match="Quote is no longer valid"):
                await TrendWorkflowService.run_step(
                    session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                    command_key="stale-price", request=request,
                )
            await session.rollback()
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user.id)) == 0
            assert await session.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) == 0
            assert (await session.get(Wallet, user.id)).balance == Decimal("10000.00")
            assert int((await session.get(AdminTrend, trend_id)).payload.get("usage_count", 0)) == 0
            row = await session.scalar(select(TrendWorkflowStep).where(TrendWorkflowStep.workflow_id == run_id, TrendWorkflowStep.ordinal == 0))
            assert row.generation_id is None and row.reserved_generation_id is None
            assert row.attempts == 0 and row.command_key is None
    finally:
        await redis.aclose()
