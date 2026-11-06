from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.api.v1 import admin_accounts, admin_auth
from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, AdminAuditLog, AdminSession, User
from app.db.session import SessionFactory
from app.services.admin_security import encrypt_mfa_secret, generate_totp_secret, hash_admin_token


@pytest_asyncio.fixture
async def actors(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "session-change-regression-key-32-characters")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    monkeypatch.setattr(settings, "admin_require_mfa", True)
    now = datetime.now(UTC)
    identities = {}
    async with SessionFactory() as session:
        await session.execute(delete(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == "support_incoming_recipients",
        ))
        for name, role in (("owner", "owner"), ("operator", "support")):
            user = User(telegram_id=7_000_000_000_000 + uuid.uuid4().int % 10**12, first_name="Session regression")
            session.add(user)
            await session.flush()
            overrides = {} if role == "owner" else {"allow": ["users.read"], "deny": ["payments.write"]}
            account = AdminAccount(
                user_id=user.id, role=role, is_active=True, permission_overrides=overrides,
                mfa_enabled=True, mfa_confirmed_at=now,
                mfa_secret_encrypted=encrypt_mfa_secret(generate_totp_secret()),
            )
            session.add(account)
            await session.flush()
            tokens = []
            for _ in range(2):
                token = uuid.uuid4().hex + uuid.uuid4().hex
                tokens.append(token)
                session.add(AdminSession(
                    admin_id=account.id, token_hash=hash_admin_token(token),
                    created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
                    idle_expires_at=now + timedelta(hours=1), step_up_until=now + timedelta(minutes=5),
                    mfa_verified=True, session_version=account.session_version,
                ))
            identities[name] = SimpleNamespace(
                id=account.id, role=role, overrides=overrides,
                version=account.session_version, tokens=tokens,
            )
        await session.commit()

    app = FastAPI()
    app.include_router(admin_accounts.router, prefix="/api/v1")
    app.include_router(admin_auth.router, prefix="/api/v1")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer " + identities["owner"].tokens[0]},
        ) as client:
            yield SimpleNamespace(client=client, **identities)
    finally:
        await redis.aclose()
        async with SessionFactory() as session:
            await session.execute(delete(AdminRuntimeSetting).where(
                AdminRuntimeSetting.key == "support_incoming_recipients",
            ))
            await session.commit()


async def _state(admin_id):
    async with SessionFactory() as session:
        account = await session.get(AdminAccount, admin_id)
        sessions = list((await session.scalars(
            select(AdminSession).where(AdminSession.admin_id == admin_id),
        )).all())
        audit = await session.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "admin.account.updated",
                AdminAuditLog.resource_id == str(admin_id),
            ).order_by(AdminAuditLog.created_at.desc()),
        )
        return account, sessions, audit


@pytest.mark.asyncio
@pytest.mark.parametrize("target_name", ["operator", "owner"])
@pytest.mark.parametrize("enabled", [True, False], ids=["subscription-change", "no-op"])
async def test_subscription_or_noop_preserves_target_and_owner_sessions(actors, target_name, enabled):
    target = getattr(actors, target_name)
    response = await actors.client.patch(f"/api/v1/admin/admins/{target.id}", json={
        "role": target.role, "is_active": True, "permission_overrides": target.overrides,
        "support_notifications": enabled, "reason": "Update only support notification preference",
    })
    assert response.status_code == 200, response.text
    assert response.json()["support_notifications"] is enabled
    account, sessions, audit = await _state(target.id)
    assert account.session_version == target.version
    assert len(sessions) == 2
    assert all(record.revoked_at is None for record in sessions)
    assert account.permission_overrides == target.overrides
    assert audit.metadata_json["sessions_revoked"] is False
    for token in [*target.tokens, actors.owner.tokens[0]]:
        current = await actors.client.get("/api/v1/admin/auth/me", headers={"Authorization": "Bearer " + token})
        assert current.status_code == 200, current.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"role": "finance"},
    {"is_active": False},
    {"permission_overrides": {"allow": ["payments.read"], "deny": []}},
], ids=["role", "active", "overrides"])
async def test_actual_privilege_change_still_revokes_all_target_sessions(actors, change):
    target = actors.operator
    response = await actors.client.patch(f"/api/v1/admin/admins/{target.id}", json={
        "role": target.role, "is_active": True, "permission_overrides": target.overrides,
        "support_notifications": False, "reason": "Owner changes administrator privileges", **change,
    })
    assert response.status_code == 200, response.text
    account, sessions, audit = await _state(target.id)
    assert account.session_version == target.version + 1
    assert len(sessions) == 2
    assert all(record.revoked_at is not None and record.revoke_reason == "privilege_changed" for record in sessions)
    assert audit.metadata_json["sessions_revoked"] is True
    for token in target.tokens:
        current = await actors.client.get("/api/v1/admin/auth/me", headers={"Authorization": "Bearer " + token})
        assert current.status_code == 401
    current = await actors.client.get("/api/v1/admin/auth/me")
    assert current.status_code == 200


@pytest.mark.asyncio
async def test_owner_ignored_override_payload_does_not_revoke_unchanged_access(actors):
    target = actors.owner
    response = await actors.client.patch(f"/api/v1/admin/admins/{target.id}", json={
        "permission_overrides": {"allow": ["users.read"]},
        "support_notifications": True, "reason": "Owner changes support notification preference",
    })
    assert response.status_code == 200, response.text
    assert response.json()["permission_overrides"] == {}
    account, sessions, audit = await _state(target.id)
    assert account.session_version == target.version
    assert all(record.revoked_at is None for record in sessions)
    assert audit.metadata_json["sessions_revoked"] is False
    current = await actors.client.get("/api/v1/admin/auth/me")
    assert current.status_code == 200
