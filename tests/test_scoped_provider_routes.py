from __future__ import annotations

import uuid
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.api.admin_deps import get_admin_context_base
from app.core.config import settings
from app.db.admin_models import AdminCommand, AdminRuntimeSetting
from app.db.models import AdminAccount, AdminSession, User, Wallet
from app.db.session import SessionFactory
from app.main import app
from app.services.generation_provider_routing import configured_routes, route_options, validate_routes
from app.services.generations import GenerationService
from app.services.generation_batches import GenerationBatchService
from app.services.batch_repository import BatchRepository
from app.services.admin_runtime import AdminRuntimeService


class WakeRedis:
    async def eval(self, *_args, **_kwargs):
        return [1, 60]

    async def rpush(self, *_args, **_kwargs):
        return 1


async def seed_policy(session, monkeypatch):
    key = f"scoped-routes-{uuid.uuid4()}"
    monkeypatch.setattr("app.services.generation_provider_routing.ROUTES_SETTING_KEY", key)
    monkeypatch.setattr("app.services.admin_runtime.ROUTES_SETTING_KEY", key)
    target, other, actor = [
        User(telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic routing user")
        for _ in range(3)
    ]
    session.add_all([target, other, actor])
    target.username = "former_synthetic_handle"
    await session.flush()
    admin = AdminAccount(user_id=actor.id, role="owner", is_active=True)
    session.add(admin)
    session.add_all([Wallet(user_id=u.id, balance=Decimal("10000")) for u in (target, other)])
    await session.flush()
    config = await configured_routes(session)
    routes = config["routes"] | {"nano-banana-pro": ["neironych", "kie"]}
    scopes = {str(target.id): {"nano-banana-pro": ["nexus", "neironych", "kie"]}}
    setting = AdminRuntimeSetting(
        key=key, value={"revision": 8, "routes": routes, "user_routes": scopes},
        updated_by_admin_id=admin.id,
    )
    session.add(setting)
    await session.commit()
    return target, other, admin, setting


async def admit(session, principal_id, **parameters):
    return await GenerationService.create(
        session, WakeRedis(), user_id=principal_id, model_id="nano-banana-pro",
        prompt="A blue ceramic cup", parameters={"aspect_ratio": "1:1", **parameters},
    )


async def test_normal_admission_uses_only_the_authenticated_users_scoped_route(monkeypatch):
    async with SessionFactory() as session:
        target, other, _admin, _setting = await seed_policy(session, monkeypatch)
        target_generation = await admit(session, target.id)
        assert target_generation.provider == "nexus"
        assert target_generation.parameters["_provider_route"] == ["nexus", "neironych", "kie"]
        assert target_generation.parameters["_provider_route_revision"] == 8
        other_generation = await admit(
            session, other.id, _provider_route=["nexus"], user_id=str(target.id),
        )
        assert other_generation.provider == "neironych"
        assert other_generation.parameters["_provider_route"] == ["neironych", "kie"]
        assert other_generation.parameters["_provider_route_revision"] == 8


async def test_batch_admission_uses_the_same_user_exception(monkeypatch):
    async with SessionFactory() as session:
        target, other, _admin, _setting = await seed_policy(session, monkeypatch)
        for user, expected in ((target, "nexus"), (other, "neironych")):
            job, replayed = await GenerationBatchService.create(
                session, WakeRedis(), user_id=user.id, model_id="nano-banana-pro",
                prompt="A blue ceramic cup", parameters={"aspect_ratio": "1:1"},
                billing_seconds=None, reference_ids=[],
                input_urls=["https://example.test/a.png", "https://example.test/b.png"],
                idempotency_key=f"scoped-batch-{uuid.uuid4()}",
            )
            assert not replayed
            rows = await BatchRepository.rows(session, job.id)
            assert len(rows) == 2
            assert all(g.provider == expected for _item, g in rows)
            assert all(g.parameters["_provider_route_revision"] == 8 for _item, g in rows)


async def test_scoped_route_admin_api_authorizes_replays_preserves_and_clears(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "synthetic-admin-key-000000000000000000000000")
    async with SessionFactory() as session:
        target, other, admin, _setting = await seed_policy(session, monkeypatch)
        now = datetime.now(UTC)
        admin.mfa_enabled = True
        admin_session = AdminSession(
            admin_id=admin.id, token_hash=uuid.uuid4().hex, created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1), idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True, step_up_until=now + timedelta(minutes=5), session_version=1,
        )
        session.add(admin_session)
        await session.commit()
        context = SimpleNamespace(
            account=admin, session=admin_session, user=await session.get(User, admin.user_id),
        )

        async def authenticated_context():
            return context

        app.dependency_overrides[get_admin_context_base] = authenticated_context
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                path = "/api/v1/admin/runtime/provider-routes"
                config = await configured_routes(session)
                scopes = {str(target.id): {"nano-banana-pro": ["nexus", "neironych", "kie"]}}
                payload = {"routes": config["routes"], "user_routes": scopes, "expected_revision": 8}
                headers = {"Idempotency-Key": str(uuid.uuid4()), "X-Admin-Confirm": "confirmed"}
                admin.role = "auditor"
                await session.commit()
                assert (await client.post(path, json=payload, headers=headers)).status_code == 403
                admin.role = "owner"
                admin_session.step_up_until = None
                await session.commit()
                assert (await client.post(path, json=payload, headers=headers)).status_code == 403
                admin_session.step_up_until = now + timedelta(minutes=5)
                await session.commit()
                assert (await client.post(path, json=payload, headers={
                    "Idempotency-Key": headers["Idempotency-Key"],
                })).status_code == 403
                for invalid in (
                    {"not-a-uuid": scopes[str(target.id)]},
                    {str(uuid.uuid4()): scopes[str(target.id)]},
                    {str(target.id): {"unknown-model": ["nexus"]}},
                    {str(target.id): {"nano-banana-pro": ["nexus", "nexus"]}},
                    {str(target.id): {"grok-video-1.5": ["nexus"]}},
                ):
                    rejected = await client.post(
                        path, json=payload | {"user_routes": invalid},
                        headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
                    )
                    assert rejected.status_code == 422, rejected.text
                saved = await client.post(path, json=payload, headers=headers)
                assert saved.status_code == 200, saved.text
                assert saved.json()["revision"] == 9
                assert saved.json()["user_routes"] == scopes
                replay = await client.post(path, json=payload, headers=headers)
                assert replay.status_code == 200 and replay.json()["idempotency_replayed"]
                assert replay.json()["user_routes"] == scopes
                assert (await client.post(path, json=payload, headers=headers | {
                    "Idempotency-Key": str(uuid.uuid4()),
                })).status_code == 422
                key = _setting.key
                assert (await client.get("/api/v1/admin/runtime")).json()[key]["user_routes"] == scopes
                legacy = await client.post(path, json={
                    "routes": config["routes"], "expected_revision": 9,
                }, headers=headers | {"Idempotency-Key": str(uuid.uuid4())})
                assert legacy.status_code == 200 and legacy.json()["user_routes"] == scopes
                old = await admit(session, target.id)
                assert old.provider == "nexus"
                target.username = "new_synthetic_handle"
                other.username = "former_synthetic_handle"
                await session.commit()
                assert (await admit(session, target.id)).provider == "nexus"
                assert (await admit(session, other.id)).provider == "neironych"
                cleared = await client.post(path, json={
                    "routes": config["routes"], "user_routes": {}, "expected_revision": 10,
                }, headers=headers | {"Idempotency-Key": str(uuid.uuid4())})
                assert cleared.status_code == 200 and cleared.json()["user_routes"] == {}
                assert (await admit(session, target.id)).provider == "neironych"
                await session.refresh(old)
                assert old.provider == "nexus" and old.parameters["_provider_route_revision"] == 10
                command = await session.scalar(select(AdminCommand).where(
                    AdminCommand.idempotency_key == headers["Idempotency-Key"],
                ))
                assert command.status == "completed" and command.request_payload["user_routes"] == scopes
        finally:
            app.dependency_overrides.pop(get_admin_context_base, None)


@pytest.mark.parametrize("model,route", [
    ("nano-banana-pro", ["neironych", "nexus", "kie"]),
    ("seedance-2.5", ["neironych", "nexus"]),
    ("gpt-image-2-t2i", ["neironych", "nexus", "kie"]),
])
def test_neironych_can_be_primary_while_retaining_the_existing_fallbacks(model, route):
    routes = {key: choices[0] for key, choices in route_options().items()}
    routes[model] = route
    assert validate_routes(routes)[model] == route


async def test_seedance_and_banana_exceptions_do_not_affect_other_users_or_gpt(monkeypatch):
    exceptions = ("seedance-2.0", "seedance-2.5", "nano-banana-pro",
                  "nano-banana-2", "nano-banana-2-lite")
    async with SessionFactory() as session:
        target, other, admin, _setting = await seed_policy(session, monkeypatch)
        config = await configured_routes(session)
        routes = config["routes"] | {
            model: ["neironych", "nexus", "kie"]
            for model in (*exceptions, "gpt-image-2-t2i")
        }
        scopes = {str(target.id): {
            model: ["nexus", "neironych", "kie"] for model in exceptions
        }}
        await AdminRuntimeService.set_provider_routes(
            session, admin=admin, routes=routes, user_routes=scopes, expected_revision=8,
            idempotency_key=str(uuid.uuid4()), request_id=str(uuid.uuid4()), confirmed=True,
        )
        await session.commit()
        for model in (*exceptions, "gpt-image-2-t2i"):
            inputs = {"aspect_ratio": "1:1"}
            if model.startswith("seedance"):
                inputs |= {"duration": 6, "resolution": "480p"}
            for user in (target, other):
                generation = await GenerationService.create(
                    session, WakeRedis(), user_id=user.id, model_id=model,
                    prompt="A blue ceramic cup", parameters=inputs,
                )
                expected = "nexus" if user.id == target.id and model in exceptions else "neironych"
                assert generation.provider == expected
                assert generation.parameters["_provider_route_revision"] == 9


async def test_concurrent_global_and_scoped_writes_share_one_revision_fence(monkeypatch):
    async with SessionFactory() as session:
        target, _other, admin, _setting = await seed_policy(session, monkeypatch)
        config = await configured_routes(session)
        admin_id = admin.id
        target_id = str(target.id)

    async def save(scopes):
        async with SessionFactory() as session:
            actor = await session.get(AdminAccount, admin_id)
            try:
                result, _replayed = await AdminRuntimeService.set_provider_routes(
                    session, admin=actor, routes=config["routes"], user_routes=scopes,
                    expected_revision=8, idempotency_key=str(uuid.uuid4()),
                    request_id=str(uuid.uuid4()), confirmed=True,
                )
                await session.commit()
                return result
            except ValueError as exc:
                await session.rollback()
                assert "changed" in str(exc)
                return None

    results = await asyncio.gather(save({target_id: {"nano-banana-pro": ["nexus", "kie"]}}), save({}))
    successful = [result for result in results if result is not None]
    assert len(successful) == 1 and successful[0]["revision"] == 9
    async with SessionFactory() as session:
        assert await configured_routes(session) == successful[0]
