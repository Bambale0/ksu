from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Generation, User, WalletTransaction
from app.db.seedance_test_models import SeedanceAdminTask
from app.db.session import SessionFactory
from app.providers.neironych_errors import NeironychProviderError
from app.providers.neironych_submission import SNAPSHOT_KEY
from app.services.generation_provider import GenerationProviderService
from app.services.generation_worker import GenerationWorkerService
from app.services.neironych_generation_provider import NeironychGenerationProviderService as Service
from app.services.seedance_admin_tasks import SeedanceAdminTaskService
from app.services.wallet import WalletService


async def generation(model="seedance-2.5", *, uncertain=False):
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Contract recovery")
        session.add(user)
        await session.flush()
        g = Generation(
            user_id=user.id,
            kind="generate",
            status="retry" if uncertain else "queued",
            prompt="Original scene",
            cost_rox=Decimal("10"),
            provider="neironych",
            parameters={
                "prompt": "Original scene",
                "aspect_ratio": "16:9",
                "duration": 4,
                "resolution": "720p" if model.startswith("seedance") else "1K",
                "_model_id": model,
                "_provider_route": [
                    "neironych",
                    "kie" if model.startswith("seedance") else "nexus",
                ],
                "_provider_route_index": 0,
            },
        )
        session.add(g)
        await session.flush()
        if uncertain:
            g.parameters = {
                **g.parameters,
                "_submission_uncertain": True,
                "_submission_uncertain_at": datetime.now(UTC).isoformat(),
            }
        await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="seed",
            idempotency_key=f"test-credit:{g.id}",
        )
        await WalletService.debit(
            session,
            user_id=user.id,
            amount=g.cost_rox,
            kind="generation",
            reference_type="generation",
            reference_id=str(g.id),
            idempotency_key=f"generation:{g.id}:charge",
        )
        await session.commit()
        return g.id


@pytest.mark.asyncio
async def test_paid_video_snapshot_is_committed_before_post_and_survives_normalizer_change(
    monkeypatch,
):
    gid = await generation()
    seen = []

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def create_video(self, **kwargs):
            async with SessionFactory() as session:
                row = await session.get(Generation, gid)
                assert row.status == "submitting"
                assert row.parameters[SNAPSHOT_KEY]["body_json"] == kwargs["request_body"]
            seen.append((kwargs["request_body"], kwargs["idempotency_key"]))
            if len(seen) == 1:
                raise httpx.ReadTimeout("lost response")
            return "original-upstream-task-" + str(gid)

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", Client)
    async with SessionFactory() as session:
        await Service.submit(session, gid)
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        row.parameters = {**row.parameters, "prompt": "Changed by future normalization"}
        await session.commit()

    def must_not_rebuild(*args):
        raise AssertionError("A saved wire body must not be reconstructed")

    monkeypatch.setattr(GenerationProviderService, "_input_for", must_not_rebuild)
    async with SessionFactory() as session:
        row = await Service.submit(session, gid)
        assert row.external_id == "original-upstream-task-" + str(gid)
        assert row.status == "generating"
        assert json.loads(seen[1][0])["prompt"] == "Original scene"
        transactions = (
            await session.scalars(
                select(WalletTransaction).where(WalletTransaction.reference_id == str(gid))
            )
        ).all()
        assert [t.kind for t in transactions] == ["generation"]
    assert seen[0] == seen[1]


@pytest.mark.asyncio
async def test_legacy_uncertain_video_without_wire_body_never_guesses_a_new_post(monkeypatch):
    gid = await generation(uncertain=True)

    def forbidden(*args):
        raise AssertionError("No provider client for a legacy unknown body")

    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychVideoClient", forbidden
    )
    async with SessionFactory() as session:
        result = await Service.submit(session, gid)
        assert result.provider == "neironych" and result.status == "retry"
        assert result.parameters["_submission_uncertain"]
        assert "body unavailable" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,http,status,provider,refund",
    [
        ("invalid_request_contract", 422, "failed", "neironych", 1),
        ("idempotency_conflict", 409, "failed", "neironych", 1),
        ("provider_rejected_request", 503, "failed", "neironych", 1),
        ("request_already_submitted", 409, "submitting", "neironych", 0),
        ("submission_outcome_unknown", 503, "submitting", "neironych", 0),
        ("provider_temporarily_unavailable", 503, "submitting", "neironych", 0),
        ("capability_mismatch", 409, "retry", "nexus", 0),
        ("insufficient_balance", 402, "retry", "nexus", 0),
        ("provider_rate_limited", 429, "retry", "nexus", 0),
    ],
)
async def test_image_disposition_metadata_and_single_refund(
    monkeypatch, code, http, status, provider, refund
):
    gid = await generation("nano-banana-pro")
    calls = []

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def create_nano_banana_pro(self, **kwargs):
            calls.append(kwargs["idempotency_key"])
            raise NeironychProviderError(
                code,
                status_code=http,
                error_code=code,
                request_id="provider-correlation-id",
                retry_after=45,
            )

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychImageClient", Client)
    async with SessionFactory() as session:
        row = await Service.submit(session, gid)
        assert (row.status, row.provider) == (status, provider)
        assert row.parameters["_provider_response"]["request_id"] == "provider-correlation-id"
        assert row.parameters["_provider_response"]["error_code"] == code
        assert row.parameters["_provider_response"]["retry_after"] == 45
        if status in {"failed", "submitting"}:
            await Service.submit(session, gid)
        transactions = (
            await session.scalars(
                select(WalletTransaction).where(WalletTransaction.reference_id == str(gid))
            )
        ).all()
        assert sum(t.kind == "generation" for t in transactions) == 1
        assert sum(t.kind == "generation_refund" for t in transactions) == refund
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_admin_retry_uses_same_durable_wire_body(monkeypatch):
    calls = []
    tid = uuid.uuid4()

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def list_models(self):
            return ["seedance-2.5"]

        async def create_video(self, **kwargs):
            calls.append((kwargs["request_body"], kwargs["idempotency_key"]))
            if len(calls) == 1:
                raise httpx.ReadTimeout("lost response")
            return "admin-original-task"

    monkeypatch.setattr("app.services.seedance_admin_tasks.NeironychVideoClient", Client)
    async with SessionFactory() as session:
        task = SeedanceAdminTask(
            id=tid,
            telegram_id=1,
            chat_id=1,
            status="queued",
            model_name="seedance-2.5",
            request_payload={"prompt": "Original scene", "duration": 4, "aspect_ratio": "16:9"},
            idempotency_key=f"admin:{tid}",
        )
        session.add(task)
        await session.commit()
    with pytest.raises(httpx.ReadTimeout):
        await SeedanceAdminTaskService._submit(tid)
    async with SessionFactory() as session:
        task = await session.get(SeedanceAdminTask, tid)
        assert task.status == "submitting"
        task.request_payload = {**task.request_payload, "prompt": "Changed later"}
        await session.commit()
    await SeedanceAdminTaskService._submit(tid)
    assert len(calls) == 2 and calls[0] == calls[1]
    async with SessionFactory() as session:
        task = await session.get(SeedanceAdminTask, tid)
        assert task.external_id == "admin-original-task"
        assert (task.available_at - datetime.now(UTC)).total_seconds() >= 8


def test_retry_after_is_not_shortened_by_generic_worker_poll():
    from types import SimpleNamespace

    g = SimpleNamespace(
        parameters={
            "_provider_response": {
                "provider": "neironych",
                "retry_after": 120,
                "at": datetime.now(UTC).isoformat(),
            }
        }
    )
    assert GenerationWorkerService._neironych_delay(g) >= 119
    assert GenerationWorkerService._neironych_delay() >= 10


def test_provider_snapshot_not_exposed_as_user_settings():
    from types import SimpleNamespace
    from app.api.v1.generations import _public_settings

    g = SimpleNamespace(
        action_type=None,
        parameters={
            "_model_id": "nano-banana-pro",
            "aspect_ratio": "16:9",
            SNAPSHOT_KEY: {"body_json": "private"},
            "_provider_response": {"request_id": "private"},
        },
    )
    assert _public_settings(g) == {"aspect_ratio": "16:9"}


@pytest.mark.asyncio
async def test_outbox_and_recovery_share_atomic_video_poll_cadence(monkeypatch):
    import asyncio

    gid = await generation()
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        row.status = "generating"
        row.external_id = "existing-provider-task-" + str(gid)
        await session.commit()
    calls = []

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def get_video(self, request_id):
            calls.append(request_id)
            await asyncio.sleep(0.05)
            return "pending", "", {}

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", Client)

    async def poll():
        async with SessionFactory() as session:
            return await Service.sync_video(
                session, request_id="existing-provider-task-" + str(gid), generation_id=gid
            )

    await asyncio.gather(poll(), poll())
    assert calls == ["existing-provider-task-" + str(gid)]


@pytest.mark.asyncio
async def test_late_pending_status_cannot_resurrect_refunded_video(monkeypatch):
    gid = await generation()
    external_id = f"pending-race-{gid}"
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        row.status = "generating"
        row.external_id = external_id
        await session.commit()

    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def get_video(self, request_id):
            async with SessionFactory() as other:
                await GenerationProviderService.fail_and_refund(
                    other, gid, "operator final failure"
                )
            return "pending", "", {}

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", Client)
    async with SessionFactory() as session:
        await Service.sync_video(session, request_id=external_id, generation_id=gid)
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        assert row.status == "failed"
        refunds = (
            await session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.reference_id == str(gid),
                    WalletTransaction.kind == "generation_refund",
                )
            )
        ).all()
        assert len(refunds) == 1
