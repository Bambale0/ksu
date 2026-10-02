import uuid
from types import SimpleNamespace

import pytest

from app.providers.neironych_video import is_failure_status
from app.services.generation_provider_routing import switch_to_fallback
from app.services.neironych_generation_provider import NeironychGenerationProviderService


class MemorySession:
    def __init__(self, generation):
        self.generation = generation

    async def scalar(self, *_args, **_kwargs):
        return self.generation

    async def get(self, *_args, **_kwargs):
        return self.generation

    async def commit(self):
        pass


def test_expired_is_terminal():
    assert is_failure_status("expired")


@pytest.mark.asyncio
async def test_uncertain_video_cannot_switch_when_circuit_opens():
    generation = SimpleNamespace(
        id=uuid.uuid4(),
        provider="neironych",
        status="submitting",
        external_id=None,
        parameters={"_provider_route": ["neironych", "kie"], "_provider_route_index": 0},
    )
    session = MemorySession(generation)
    await NeironychGenerationProviderService._mark_video_retry(
        session,
        generation,
        error="response lost after server accepted POST",
    )
    result = await switch_to_fallback(session, generation.id, reason="circuit open")
    assert result is None
    assert generation.provider == "neironych"
    assert generation.parameters["_submission_uncertain"] is True


@pytest.mark.asyncio
async def test_bound_task_cannot_switch_without_terminal_evidence():
    generation = SimpleNamespace(
        id=uuid.uuid4(),
        provider="nexus",
        status="generating",
        external_id="accepted-task",
        parameters={"_provider_route": ["nexus", "neironych"], "_provider_route_index": 0},
    )
    assert await switch_to_fallback(MemorySession(generation), generation.id, reason="slow") is None
    assert generation.external_id == "accepted-task"


@pytest.mark.asyncio
async def test_late_submit_error_keeps_concurrently_bound_task(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services.generation_provider import GenerationProviderService

    generation = SimpleNamespace(
        id=uuid.uuid4(),
        provider="neironych",
        status="generating",
        external_id="concurrently-bound-task",
        parameters={
            "_model_id": "seedance-2.5",
            "_provider_route": ["neironych", "kie"],
            "_provider_route_index": 0,
        },
    )
    refund = AsyncMock()
    monkeypatch.setattr(GenerationProviderService, "fail_and_refund", refund)
    result = await NeironychGenerationProviderService._fallback_or_fail(
        MemorySession(generation),
        generation,
        reason="Neironych API HTTP 429: rate limited",
    )
    assert result is generation
    assert generation.provider == "neironych"
    refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_status", ["queued", "submitting"])
async def test_worker_recovers_lost_video_response_without_switch(monkeypatch, initial_status):
    from decimal import Decimal
    from unittest.mock import AsyncMock
    import httpx
    from app.db.models import Generation, User
    from app.db.session import SessionFactory
    from app.services.generation_reliability import ClaimedGeneration, GenerationOutboxService
    from app.services.generation_worker import GenerationWorkerService
    from app.services.abuse_protection import AbuseProtectionService, ProviderCircuitOpen

    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Safety test")
        session.add(user)
        await session.flush()
        g = Generation(
            user_id=user.id,
            kind="text_to_video",
            status=initial_status,
            prompt="A moving cloud",
            cost_rox=Decimal("0"),
            provider="neironych",
            parameters={
                "_model_id": "seedance-2.5",
                "_provider_route": ["neironych", "kie"],
                "_provider_route_index": 0,
                "prompt": "A moving cloud",
                "duration": 4,
                "resolution": "480p",
                "aspect_ratio": "16:9",
            },
        )
        session.add(g)
        await session.flush()
        outbox = GenerationOutboxService.add(session, g.id)
        await session.flush()
        claim = ClaimedGeneration(outbox.id, g.id, 1)
        gid = g.id
        if initial_status == "submitting":
            # A new-version worker persists wire bytes before it can crash in
            # submitting. Legacy rows without those bytes have a separate
            # fail-closed regression and must not guess a replacement body.
            from app.core.config import settings
            from app.providers.neironych_submission import freeze_submission
            from app.services.generation_provider_routing import idempotency_key
            body = {"prompt": g.prompt, "duration": 4, "resolution": "480p", "aspect_ratio": "16:9"}
            g.parameters = {**g.parameters, "_neironych_submission": freeze_submission(
                model="seedance-2.5", payload=body, key=idempotency_key(g),
                base_url=settings.neironych_api_base_url)}
        await session.commit()
    keys = []

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def create_video(self, **kwargs):
            keys.append(kwargs["idempotency_key"])
            if len(keys) == 1:
                raise httpx.ReadTimeout("accepted but response lost")
            return "recovered-" + str(gid)

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", Client)
    monkeypatch.setattr(GenerationOutboxService, "claim", AsyncMock(return_value=claim))
    gate = AsyncMock()
    monkeypatch.setattr(AbuseProtectionService, "provider_submission_gate", gate)
    monkeypatch.setattr(AbuseProtectionService, "record_provider_success", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "record_provider_failure", AsyncMock())
    await GenerationWorkerService.process_one(None)
    async with SessionFactory() as session:
        g = await session.get(Generation, gid)
        assert g.provider == "neironych" and g.status == "retry"
        assert g.parameters["_submission_uncertain"]
    # Open circuit after an upstream task might exist: no provider switch.
    gate.side_effect = ProviderCircuitOpen("neironych", retry_after=30)
    await GenerationWorkerService.process_one(None)
    async with SessionFactory() as session:
        g = await session.get(Generation, gid)
        assert g.provider == "neironych" and g.external_id is None
    gate.side_effect = None
    await GenerationWorkerService.process_one(None)
    assert len(keys) == 2 and keys[0] == keys[1]
    async with SessionFactory() as session:
        g = await session.get(Generation, gid)
        assert g.external_id == "recovered-" + str(gid)
        assert g.status == "generating"
        assert not g.parameters.get("_submission_uncertain")
        await GenerationOutboxService.mark_generation_terminal(session, gid, failed=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "upstream_state,error,expected_provider,expected_status",
    [
        ("expired", "", "kie", "retry"),
        ("failed", "provider_generation_failed", "neironych", "failed"),
        ("failed", "copyright restrictions", "neironych", "failed"),
    ],
)
async def test_terminal_video_outcome_and_refund(
    monkeypatch, upstream_state, error, expected_provider, expected_status
):
    from decimal import Decimal
    from sqlalchemy import select
    from app.db.models import Generation, User, WalletTransaction
    from app.db.session import SessionFactory
    from app.services.generation_reliability import GenerationOutboxService
    from app.services.generation_provider import GenerationProviderService
    from app.services.wallet import WalletService

    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Terminal test")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        g = Generation(
            user_id=user.id,
            kind="text_to_video",
            status="generating",
            prompt="cloud",
            cost_rox=Decimal("9"),
            provider="neironych",
            external_id=str(uuid.uuid4()),
            parameters={
                "_model_id": "seedance-2.5",
                "_provider_route": ["neironych", "kie"],
                "_provider_route_index": 0,
            },
        )
        session.add(g)
        await session.flush()
        GenerationOutboxService.add(session, g.id)
        gid, external_id = g.id, g.external_id
        await session.commit()

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def get_video(self, request_id):
            return upstream_state, error, {}

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", Client)
    async with SessionFactory() as session:
        g = await NeironychGenerationProviderService.sync_video(
            session, request_id=external_id, generation_id=gid
        )
        assert (g.provider, g.status) == (expected_provider, expected_status)
        if upstream_state == "expired":
            assert g.parameters["_provider_attempts"][0]["external_id"] == external_id
            rows = list(
                (
                    await session.scalars(
                        select(WalletTransaction).where(WalletTransaction.reference_id == str(gid))
                    )
                ).all()
            )
            assert not rows  # No refund while fallback remains viable.
        await GenerationProviderService.fail_and_refund(session, gid, "final failure")
        await GenerationProviderService.fail_and_refund(session, gid, "duplicate terminal delivery")
        rows = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.reference_id == str(gid),
                        WalletTransaction.kind == "generation_refund",
                    )
                )
            ).all()
        )
        assert len(rows) == 1 and rows[0].amount == Decimal("9")


@pytest.mark.asyncio
async def test_late_download_cannot_resurrect_refunded_generation():
    from decimal import Decimal
    from pathlib import Path
    from app.db.models import Generation, User
    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Late result")
        session.add(user)
        await session.flush()
        g = Generation(
            user_id=user.id,
            kind="text_to_video",
            status="generating",
            prompt="cloud",
            cost_rox=Decimal("0"),
            provider="neironych",
        )
        session.add(g)
        await session.commit()
        gid = g.id
        async with SessionFactory() as other:
            current = await other.get(Generation, gid)
            current.status = "failed"
            await other.commit()
        result = await NeironychGenerationProviderService._complete_local_file(
            session,
            gid,
            path=Path("must-not-be-read.mp4"),
            content_type="video/mp4",
            source_url="neironych://video/late",
        )
        assert result.status == "failed" and result.result_url is None
