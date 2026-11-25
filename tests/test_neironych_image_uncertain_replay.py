"""Recover an interrupted Neironych image HTTP response by immutable idempotent replay."""

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models import Generation, User
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.providers.neironych_submission import SNAPSHOT_KEY
from app.services.abuse_protection import AbuseProtectionService, ProviderCircuitOpen
from app.services.generation_reliability import ClaimedGeneration, GenerationOutboxService
from app.services.generation_worker import GenerationWorkerService
from app.services.neironych_generation_provider import NeironychGenerationProviderService


async def _lost_image(*, frozen=True, next_recovery=None, provider="neironych"):
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(6_000_000_000_000, 7_999_999_999_999),
            first_name="Image recovery test",
        )
        session.add(user)
        await session.flush()
        parameters = {
            "_model_id": "nano-banana-pro",
            "_provider_route": ["neironych", "nexus", "kie"],
            "_provider_route_index": 0,
            "_submission_uncertain": True,
        }
        if frozen:
            parameters[SNAPSHOT_KEY] = {
                "body_json": '{"model":"nano-banana-pro","prompt":"frozen"}',
                "idempotency_key": "immutable-idempotency-key",
            }
        if next_recovery is not None:
            parameters["_neironych_image_recovery_next_at"] = next_recovery.isoformat()
        gen = Generation(
            user_id=user.id,
            kind="image_to_image",
            status="submitting",
            prompt="Original",
            provider=provider,
            cost_rox=Decimal("0"),
            parameters=parameters,
        )
        session.add(gen)
        await session.flush()
        outbox = GenerationOutboxService.add(session, gen.id)
        await session.flush()
        gen.updated_at = datetime.now(timezone.utc) - timedelta(seconds=105)
        await session.commit()
        return gen.id, outbox.id


async def _claim_target(monkeypatch, gid, outbox_id):
    async def claim(_session):
        return ClaimedGeneration(outbox_id=outbox_id, generation_id=gid, attempts=2)

    monkeypatch.setattr(GenerationOutboxService, "claim", claim)


@pytest.mark.asyncio
async def test_lost_neironych_image_response_replays_exact_frozen_request(monkeypatch):
    gid, outbox_id = await _lost_image()
    await _claim_target(monkeypatch, gid, outbox_id)
    gate = AsyncMock()
    submit = AsyncMock()
    failure = AsyncMock()
    monkeypatch.setattr(AbuseProtectionService, "provider_submission_gate", gate)
    monkeypatch.setattr(AbuseProtectionService, "record_provider_failure", failure)

    async def fake_submit(session, actual_id):
        assert actual_id == gid
        row = await session.get(Generation, gid)
        assert row.status == "retry"
        assert row.parameters["_submission_uncertain"] is True
        assert row.parameters[SNAPSHOT_KEY]["idempotency_key"] == "immutable-idempotency-key"
        return row

    submit.side_effect = fake_submit
    monkeypatch.setattr(NeironychGenerationProviderService, "submit", submit)
    assert await GenerationWorkerService.process_one(None) is True
    submit.assert_awaited_once()
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == gid)
        )
        assert row is not None and row.provider == "neironych"
        assert row.parameters[SNAPSHOT_KEY]["body_json"] == '{"model":"nano-banana-pro","prompt":"frozen"}'
        assert row.parameters["_submission_uncertain_at"]
        assert row.parameters["_neironych_image_recovery_next_at"]
        assert outbox is not None and outbox.status == "pending"


@pytest.mark.asyncio
async def test_image_recovery_waits_for_cadence_without_extra_post(monkeypatch):
    gid, outbox_id = await _lost_image(
        next_recovery=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    await _claim_target(monkeypatch, gid, outbox_id)
    submit = AsyncMock()
    monkeypatch.setattr(NeironychGenerationProviderService, "submit", submit)
    assert await GenerationWorkerService.process_one(None) is True
    submit.assert_not_awaited()
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        assert row is not None and row.status == "submitting"


@pytest.mark.asyncio
async def test_legacy_uncertain_image_without_snapshot_must_not_repost(monkeypatch):
    gid, outbox_id = await _lost_image(frozen=False)
    await _claim_target(monkeypatch, gid, outbox_id)
    submit = AsyncMock()
    monkeypatch.setattr(NeironychGenerationProviderService, "submit", submit)
    assert await GenerationWorkerService.process_one(None) is True
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_circuit_open_does_not_spend_on_backup_during_image_recovery(monkeypatch):
    gid, outbox_id = await _lost_image()
    await _claim_target(monkeypatch, gid, outbox_id)

    async def denied(*_args, **_kwargs):
        raise ProviderCircuitOpen("temporarily down", retry_after=30)

    monkeypatch.setattr(AbuseProtectionService, "provider_submission_gate", denied)
    submit = AsyncMock()
    monkeypatch.setattr(NeironychGenerationProviderService, "submit", submit)
    # Any fallback would be a second potentially paid generation.
    fallback = AsyncMock(side_effect=AssertionError("must not switch provider"))
    monkeypatch.setattr("app.services.generation_worker.switch_to_fallback", fallback)
    assert await GenerationWorkerService.process_one(None) is True
    submit.assert_not_awaited()
    fallback.assert_not_awaited()
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        assert row is not None and row.provider == "neironych"
