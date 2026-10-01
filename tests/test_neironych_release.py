import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.api.admin_deps import get_admin_context_base
from app.core.config import settings
from app.db.admin_models import AdminCommand
from app.db.models import AdminAccount, AdminSession, Generation, User, Wallet
from app.db.session import SessionFactory
from app.main import app
from app.providers.nexus import NexusTask
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import (
    configured_routes,
    route_for_model,
    validate_routes,
)
from app.services.generations import GenerationService
from app.services.nexus_generation_provider import NexusGenerationProviderService
from app.services.wallet import WalletService


def test_nano_default_keeps_nexus_primary():
    assert route_for_model("nano-banana-pro") == ("nexus", "neironych")


@pytest.mark.parametrize("route", [[], ["nexus", "nexus"], ["kie"], ["neironych", "nexus"]])
def test_unsupported_nano_routes_fail_closed(route):
    with pytest.raises(ValueError):
        validate_routes(
            {"seedance-2.0": ["neironych"], "seedance-2.5": ["kie"], "nano-banana-pro": route}
        )


class WakeRedis:
    async def eval(self, *_args, **_kwargs):
        return [1, 60]

    async def rpush(self, *_args, **_kwargs):
        return 1


@pytest.mark.asyncio
async def test_runtime_route_api_permissions_revision_replay_and_frozen_jobs(monkeypatch):
    # A unique setting key leaves all other tests on the bootstrap routes.
    key = f"route-test-{uuid.uuid4()}"
    monkeypatch.setattr("app.services.generation_provider_routing.ROUTES_SETTING_KEY", key)
    monkeypatch.setattr("app.services.admin_runtime.ROUTES_SETTING_KEY", key)
    monkeypatch.setattr(
        settings, "admin_security_key", "test-admin-security-key-0000000000000000000000"
    )
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Route admin")
        session.add(user)
        await session.flush()
        admin = AdminAccount(
            user_id=user.id,
            role="auditor",
            is_active=True,
            mfa_enabled=True,
            permission_overrides={},
        )
        session.add(admin)
        await session.flush()
        now = datetime.now(UTC)
        admin_session = AdminSession(
            admin_id=admin.id,
            token_hash=uuid.uuid4().hex,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True,
            step_up_until=now + timedelta(minutes=5),
            session_version=1,
        )
        session.add(admin_session)
        await WalletService.ensure_wallet(session, user.id)
        await session.commit()
        context = SimpleNamespace(account=admin, session=admin_session, user=user)
        before = await configured_routes(session)
        routes = before["routes"] | {"nano-banana-pro": ["neironych"]}

        async def authenticated_context():
            return context

        app.dependency_overrides[get_admin_context_base] = authenticated_context
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                path = "/api/v1/admin/runtime/provider-routes"
                payload = {"routes": routes, "expected_revision": 1}
                idem = f"route-change-{uuid.uuid4()}"
                headers = {"Idempotency-Key": idem, "X-Admin-Confirm": "confirmed"}
                denied = await client.post(path, json=payload, headers=headers)
                assert denied.status_code == 403
                admin.role = "admin"
                admin_session.step_up_until = None
                await session.commit()
                denied = await client.post(path, json=payload, headers=headers)
                assert denied.status_code == 403 and "step-up" in denied.text
                admin_session.step_up_until = now + timedelta(minutes=5)
                await session.commit()
                denied = await client.post(path, json=payload, headers={"Idempotency-Key": idem})
                assert denied.status_code == 403
                assert (await client.post(path, json=payload)).status_code == 400
                old = await GenerationService.create(
                    session,
                    WakeRedis(),
                    user_id=user.id,
                    model_id="nano-banana-pro",
                    prompt="old snapshot",
                )
                assert old.provider == "nexus"
                first = await client.post(path, json=payload, headers=headers)
                assert first.status_code == 200, first.text
                assert first.json()["revision"] == 2
                replay = await client.post(path, json=payload, headers=headers)
                assert replay.status_code == 200 and replay.json()["idempotency_replayed"]
                stale = await client.post(
                    path, json=payload, headers=headers | {"Idempotency-Key": str(uuid.uuid4())}
                )
                assert stale.status_code == 422
                current = await client.get("/api/v1/admin/runtime")
                assert current.status_code == 200
                assert current.json()[key]["routes"] == routes
                new = await GenerationService.create(
                    session,
                    WakeRedis(),
                    user_id=user.id,
                    model_id="nano-banana-pro",
                    prompt="new snapshot",
                )
                assert new.provider == "neironych"
                assert new.parameters["_provider_route_revision"] == 2
                await session.refresh(old)
                assert old.provider == "nexus" and old.parameters["_provider_route_revision"] == 1
                command = await session.scalar(
                    select(AdminCommand).where(AdminCommand.idempotency_key == idem)
                )
                assert command.status == "completed" and command.admin_user_id == admin.id
        finally:
            app.dependency_overrides.pop(get_admin_context_base, None)


async def create_nexus_job(session):
    user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Fallback test")
    session.add(user)
    await session.flush()
    await WalletService.ensure_wallet(session, user.id)
    await WalletService.credit(
        session,
        user_id=user.id,
        amount=Decimal("100"),
        kind="test_credit",
        idempotency_key=str(uuid.uuid4()),
    )
    g = Generation(
        user_id=user.id,
        provider="nexus",
        kind="text_to_image",
        status="queued",
        prompt="a cloud",
        cost_rox=Decimal("25"),
        parameters={
            "_model_id": "nano-banana-pro",
            "_provider_route": ["nexus", "neironych"],
            "_provider_route_index": 0,
        },
    )
    session.add(g)
    await session.flush()
    await WalletService.debit(
        session,
        user_id=user.id,
        amount=Decimal("25"),
        kind="generation",
        idempotency_key=f"generation:{g.id}",
    )
    await session.commit()
    return g


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 402, 404, 429, 400, 403, 409, 500])
async def test_nexus_submit_failure_route_and_wallet(monkeypatch, code):
    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def create_nano_banana(self, **kwargs):
            response = httpx.Response(
                code, request=httpx.Request("POST", "https://nexus.example/generate")
            )
            response.raise_for_status()

    monkeypatch.setattr("app.services.nexus_generation_provider.NexusClient", Client)
    async with SessionFactory() as session:
        g = await create_nexus_job(session)
        if code in {401, 402, 404, 429}:
            result = await NexusGenerationProviderService.submit(session, g.id)
            assert result.provider == "neironych" and result.status == "retry"
            assert result.parameters["_provider_attempts"][0]["provider"] == "nexus"
        else:
            with pytest.raises(httpx.HTTPStatusError):
                await NexusGenerationProviderService.submit(session, g.id)
            assert g.provider == "nexus"
            if code == 500:
                assert g.parameters["_submission_uncertain"]
                # A later availability response cannot erase the earlier ambiguity.
                err = httpx.HTTPStatusError(
                    "rate limited",
                    request=httpx.Request("POST", "https://nexus.example"),
                    response=httpx.Response(429),
                )
                await NexusGenerationProviderService._record_submission_error(session, g.id, err)
                assert g.provider == "nexus" and g.parameters["_submission_uncertain"]
        await session.refresh(g)
        wallet = await session.get(Wallet, g.user_id)
        assert wallet.balance == (Decimal("100") if code in {400, 403, 409} else Decimal("75"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,fallback",
    [
        ("internal server error", True),
        ("provider_generation_failed", False),
        ("safety policy timeout", False),
    ],
)
async def test_nexus_terminal_fallback_preserves_wallet_until_final_failure(
    monkeypatch, reason, fallback
):
    class Client:
        def __init__(self, *args):
            pass

        async def aclose(self):
            pass

        async def get_task(self, task_id):
            return NexusTask(task_id=task_id, status="failed", image_urls=[], error=reason)

    monkeypatch.setattr("app.services.nexus_generation_provider.NexusClient", Client)
    async with SessionFactory() as session:
        g = await create_nexus_job(session)
        g.status = "generating"
        g.external_id = f"nexus-{uuid.uuid4()}"
        original_task = g.external_id
        await session.commit()
        await NexusGenerationProviderService.sync_task(
            session, task_id=original_task, generation_id=g.id
        )
        wallet = await session.get(Wallet, g.user_id)
        await session.refresh(wallet)
        assert g.provider == ("neironych" if fallback else "nexus")
        assert wallet.balance == (Decimal("75") if fallback else Decimal("100"))
        if fallback:
            assert g.parameters["_provider_attempts"][0]["external_id"] == original_task
        await GenerationProviderService.fail_and_refund(session, g.id, "final error")
        await GenerationProviderService.fail_and_refund(session, g.id, "repeat")
        await session.refresh(wallet)
        assert wallet.balance == Decimal("100")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["bound", "switched"])
async def test_nexus_late_error_does_not_overwrite_newer_attempt(monkeypatch, state):
    g = SimpleNamespace(
        provider="nexus" if state == "bound" else "neironych",
        status="generating",
        external_id="accepted-task",
        parameters={},
        id=uuid.uuid4(),
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=g), get=AsyncMock(return_value=g), commit=AsyncMock()
    )
    refund = AsyncMock()
    monkeypatch.setattr(GenerationProviderService, "fail_and_refund", refund)
    err = httpx.HTTPStatusError(
        "unavailable",
        request=httpx.Request("POST", "https://nexus.example"),
        response=httpx.Response(401),
    )
    await NexusGenerationProviderService._record_submission_error(session, g.id, err)
    refund.assert_not_awaited()
    assert g.external_id == "accepted-task"


@pytest.mark.asyncio
async def test_late_neironych_image_error_cannot_resurrect_refunded_task():
    from app.services.neironych_generation_provider import NeironychGenerationProviderService

    async with SessionFactory() as session:
        g = await create_nexus_job(session)
        g.provider = "neironych"
        g.status = "submitting"
        await session.commit()
        async with SessionFactory() as other:
            await GenerationProviderService.fail_and_refund(other, g.id, "recovery timeout")
        result = await NeironychGenerationProviderService._mark_image_uncertain(
            session,
            g,
            error="late transport timeout",
        )
        assert result.status == "failed"
        wallet = await session.get(Wallet, g.user_id)
        assert wallet.balance == Decimal("100")
