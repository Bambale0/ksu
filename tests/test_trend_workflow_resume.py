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


@pytest.mark.parametrize("metadata", [
    {"schema_version": 2, "description": "Updated"},
    {"workflow_type": "sequential_photo_video", "description": "Updated"},
])
def test_metadata_update_can_echo_version_without_losing_steps(metadata) -> None:
    existing = _recipe()
    merged = TrendWorkflowService.merge_admin_payload(existing, metadata)
    result = TrendWorkflowService.normalize_recipe("Updated title", merged)
    assert result["description"] == "Updated"
    assert result["steps"][0]["prompt"] == "PRIVATE_STEP_PHOTO"
    assert result["steps"][1]["model_id"] == "seedance-2.5"


@pytest.mark.asyncio
async def test_failed_attempt_requires_explicit_paid_retry_intent() -> None:
    from sqlalchemy import func, select
    from app.db.models import WalletTransaction
    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    body = {"image_inputs": [{"slot_id": "person_photo", "url": "https://example.invalid/user.jpg"}], "values": {}}
    try:
        async with SessionFactory() as session:
            quote = await TrendWorkflowService.quote_step(session, run_id=run_id, step_key="photo", user_id=user.id, request=body)
            body["quoted_cost_rox"] = quote["cost_rox"]
            step = await TrendWorkflowService.run_step(session, redis, run_id=run_id, step_key="photo", user_id=user.id, command_key="first", request=body)
            gen = await session.get(Generation, step.generation_id)
            gen.status = "failed"
            gen.error = "Synthetic provider rejection"
            await session.commit()
        async with SessionFactory() as session:
            with pytest.raises(ValueError, match="retry"):
                await TrendWorkflowService.run_step(session, redis, run_id=run_id, step_key="photo", user_id=user.id, command_key="new-key-without-consent", request=body)
            await session.rollback()
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user.id)) == 1
            assert await session.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) == 1
    finally:
        await redis.aclose()


async def _ready_photos(user, run_id, redis, tmp_path):
    from PIL import Image
    from app.services.media_assets import MediaAssetService
    body = {"image_inputs": [{"slot_id": "person_photo", "url": "https://example.invalid/user.jpg"}], "values": {}}
    async with SessionFactory() as session:
        quote = await TrendWorkflowService.quote_step(session, run_id=run_id, step_key="photo", user_id=user.id, request=body)
        body["quoted_cost_rox"] = quote["cost_rox"]
        step = await TrendWorkflowService.run_step(session, redis, run_id=run_id, step_key="photo", user_id=user.id, command_key="photo", request=body)
        gen = await session.get(Generation, step.generation_id)
        gen.status = "succeeded"
        gen.result_url = "https://expired.invalid/photo.png"
        ids = []
        for ordinal in range(2):
            path = tmp_path / f"photo-{ordinal}.png"
            Image.new("RGB", (16, 16), (40 + ordinal * 20, 70, 90)).save(path)
            asset = await MediaAssetService.persist_ready_local_file(session, gen, path=path, content_type="image/png", source_url=f"https://expired.invalid/photo-{ordinal}.png", ordinal=ordinal)
            ids.append(asset.id)
        await session.commit()
        return ids, body, gen.id


@pytest.mark.asyncio
async def test_selected_second_photo_survives_video_start_and_owner_reload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "owned"))
    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    try:
        assets, _body, _photo_gen = await _ready_photos(user, run_id, redis, tmp_path)
        video = {"media_asset_id": str(assets[1]), "values": {}}
        async with SessionFactory() as session:
            quote = await TrendWorkflowService.quote_step(session, run_id=run_id, step_key="video", user_id=user.id, request=video)
            video["quoted_cost_rox"] = quote["cost_rox"]
            await TrendWorkflowService.run_step(session, redis, run_id=run_id, step_key="video", user_id=user.id, command_key="video", request=video)
        async with SessionFactory() as session:
            view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            assert view["steps"][0]["media_asset_id"] == str(assets[1])
            assert view["steps"][0]["media"]["id"] == str(assets[1])
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_photo_redo_retains_previous_owned_media_in_attempt_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "owned"))
    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    try:
        assets, body, old_id = await _ready_photos(user, run_id, redis, tmp_path)
        async with SessionFactory() as session:
            await TrendWorkflowService.run_step(session, redis, run_id=run_id, step_key="photo", user_id=user.id, command_key="explicit-photo-redo", request={**body, "retry": True})
        async with SessionFactory() as session:
            view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            previous = view["steps"][0]["attempt_history"][0]
            assert previous["generation_id"] == str(old_id)
            assert previous["media"] is not None
            assert previous["media"]["id"] == str(assets[0])
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_admin_save_cannot_reset_usage_and_command_replay_ignores_live_counter() -> None:
    _user, author, trend_id, _run_id = await _scenario()
    async with SessionFactory() as session:
        row = await session.get(AdminTrend, trend_id)
        row.payload = {**row.payload, "usage_count": 8}
        await session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def current_user():
        return author

    app.dependency_overrides[get_current_user] = current_user
    body = {"title": "Edited title", "payload": {**_recipe(), "usage_count": 0}, "is_active": True}
    headers = {"Idempotency-Key": f"controller-admin-metadata-save-{uuid.uuid4()}"}
    async with AsyncClient(transport=ASGITransport(app), base_url="http://workflow.test") as client:
        response = await client.patch(f"/api/v1/trends/manage/{trend_id}", json=body, headers=headers)
        assert response.status_code == 200, response.text
        async with SessionFactory() as session:
            row = await session.get(AdminTrend, trend_id)
            assert row.payload["usage_count"] == 8
            row.payload = {**row.payload, "usage_count": 9}
            await session.commit()
        response = await client.patch(f"/api/v1/trends/manage/{trend_id}", json=body, headers=headers)
        assert response.status_code == 200, response.text
        async with SessionFactory() as session:
            assert (await session.get(AdminTrend, trend_id)).payload["usage_count"] == 9


@pytest.mark.asyncio
async def test_real_admin_model_catalog_exposes_form_schema_not_mock_only_fields() -> None:
    _user, author, _trend_id, _run_id = await _scenario()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def current_user():
        return author

    app.dependency_overrides[get_current_user] = current_user
    async with AsyncClient(transport=ASGITransport(app), base_url="http://workflow.test") as client:
        response = await client.get("/api/v1/trends/manage")
        assert response.status_code == 200, response.text
        models = {model["id"]: model for model in response.json()["models"]}
        video = models["seedance-2.5"]
        assert video["ui_schema"]["defaults"]["duration"] > 0
        assert any(field["name"] == "duration" for field in video["ui_schema"]["fields"])
        assert models["nano-banana-pro"]["ui_schema"]["defaults"]["resolution"]
    from app.api.v1.admin_trends import web_admin_trend_options
    web_models = {model["id"]: model for model in (await web_admin_trend_options(None))["models"]}
    assert web_models["seedance-2.5"]["ui_schema"] == video["ui_schema"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_available", [True, False])
@pytest.mark.parametrize("legacy_selection", [True, False])
async def test_video_retry_without_asset_uses_persisted_photo_or_fails_closed(
    tmp_path, monkeypatch, source_available: bool, legacy_selection: bool,
) -> None:
    from sqlalchemy import func, select
    from app.db.media_models import MediaAsset
    from app.db.models import WalletTransaction
    from app.db.trend_workflow_models import TrendWorkflowStep

    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "owned"))
    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    try:
        assets, _body, _photo_id = await _ready_photos(user, run_id, redis, tmp_path)
        first_request = {"media_asset_id": str(assets[1]), "values": {}}
        async with SessionFactory() as session:
            quote = await TrendWorkflowService.quote_step(
                session, run_id=run_id, step_key="video", user_id=user.id,
                request=first_request,
            )
            first_request["quoted_cost_rox"] = quote["cost_rox"]
            step = await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="video", user_id=user.id,
                command_key="selected-source-first", request=first_request,
            )
            generation = await session.get(Generation, step.generation_id)
            generation.status = "failed"
            generation.error = "Synthetic failure after source selection"
            if legacy_selection:
                photo_step = await session.scalar(select(TrendWorkflowStep).where(
                    TrendWorkflowStep.workflow_id == run_id, TrendWorkflowStep.ordinal == 0,
                ))
                photo_step.media_asset_id = None
            balance_before = (await session.get(Wallet, user.id)).balance
            if not source_available:
                selected = await session.get(MediaAsset, assets[1])
                selected.status = "failed"
            await session.commit()

        retry_request = {"values": {}, "retry": True}
        async with SessionFactory() as session:
            if not source_available:
                with pytest.raises(ValueError, match="ready owned image"):
                    await TrendWorkflowService.quote_step(
                        session, run_id=run_id, step_key="video", user_id=user.id,
                        request=retry_request,
                    )
                with pytest.raises(ValueError, match="ready owned image"):
                    await TrendWorkflowService.run_step(
                        session, redis, run_id=run_id, step_key="video", user_id=user.id,
                        command_key="unavailable-source-retry",
                        request={**retry_request, "quoted_cost_rox": first_request["quoted_cost_rox"]},
                    )
                await session.rollback()
                assert await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user.id)) == 2
                assert await session.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) == 2
                assert (await session.get(Wallet, user.id)).balance == balance_before
                return
            quote = await TrendWorkflowService.quote_step(
                session, run_id=run_id, step_key="video", user_id=user.id,
                request=retry_request,
            )
            retry_request["quoted_cost_rox"] = quote["cost_rox"]
            step = await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="video", user_id=user.id,
                command_key="selected-source-retry", request=retry_request,
            )
            generation = await session.get(Generation, step.generation_id)
            assert generation.parameters["reference_image_urls"] == [f"ksu-media://{assets[1]}"]
        async with SessionFactory() as session:
            view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            assert view["steps"][0]["media_asset_id"] == str(assets[1])
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_owner_receipts_correlate_current_and_prior_paid_intents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "owned"))
    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    try:
        _assets, body, _photo_id = await _ready_photos(user, run_id, redis, tmp_path)
        async with SessionFactory() as session:
            first = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            assert first["steps"][0]["command_id"] == "photo"
            await TrendWorkflowService.run_step(
                session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                command_key="photo-explicit-next-attempt", request={**body, "retry": True},
            )
        async with SessionFactory() as session:
            view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            photo = view["steps"][0]
            assert photo["command_id"] == "photo-explicit-next-attempt"
            assert photo["attempt_history"][0]["command_id"] == "photo"
            serialized = repr(view)
            assert "payload_hash" not in serialized and "request_hash" not in serialized
            assert "PRIVATE_STEP" not in serialized
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_corrected_payload_and_delayed_original_share_one_paid_intent() -> None:
    import asyncio
    from sqlalchemy import func, select
    from app.db.models import WalletTransaction
    from app.services.trend_workflows import TrendWorkflowConflict

    user, _author, _trend_id, run_id = await _scenario()
    redis = Redis.from_url(settings.redis_url)
    bodies = [
        {"image_inputs": [{"slot_id": "person_photo", "url": f"https://example.invalid/{name}.jpg"}], "values": {}}
        for name in ("original-input", "reentered-input")
    ]
    try:
        for body in bodies:
            async with SessionFactory() as session:
                quote = await TrendWorkflowService.quote_step(
                    session, run_id=run_id, step_key="photo", user_id=user.id, request=body,
                )
                body["quoted_cost_rox"] = quote["cost_rox"]

        async def submit(body):
            async with SessionFactory() as session:
                return await TrendWorkflowService.run_step(
                    session, redis, run_id=run_id, step_key="photo", user_id=user.id,
                    command_key="same-unresolved-intent", request=body,
                )

        results = await asyncio.gather(*(submit(body) for body in bodies), return_exceptions=True)
        assert sum(isinstance(result, TrendWorkflowConflict) for result in results) == 1
        assert sum(not isinstance(result, BaseException) for result in results) == 1
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user.id)) == 1
            assert await session.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user.id)) == 1
            view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user.id)
            assert view["steps"][0]["command_id"] == "same-unresolved-intent"
    finally:
        await redis.aclose()
