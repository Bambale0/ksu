from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.router import api_router
from app.core.config import settings
from app.db.models import AdminAccount, AdminAuditLog, AdminSession, User
from app.db.session import SessionFactory

PATH = "/api/v1/admin/security/sessions/{session_id}"


@pytest.fixture(autouse=True)
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "isolated-session-revocation-regression-key")


async def actors(*, fresh: bool = True, role: str = "owner"):
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        user = User(telegram_id=9_100_000_000_000 + uuid.uuid4().int % 100_000_000_000)
        session.add(user)
        await session.flush()
        account = AdminAccount(
            user_id=user.id, role=role, permission_overrides={}, is_active=True, mfa_enabled=True,
        )
        session.add(account)
        await session.flush()
        values = {
            "admin_id": account.id,
            "created_at": now,
            "last_seen_at": now,
            "expires_at": now + timedelta(hours=1),
            "idle_expires_at": now + timedelta(hours=1),
            "mfa_verified": True,
            "session_version": 1,
        }
        actor_session = AdminSession(
            **values, token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            step_up_until=now + timedelta(minutes=5) if fresh else now - timedelta(seconds=1),
        )
        target = AdminSession(**values, token_hash=uuid.uuid4().hex + uuid.uuid4().hex)
        session.add_all([actor_session, target])
        await session.commit()
        return AdminContext(account=account, session=actor_session, user=user), target.id


@asynccontextmanager
async def client_for(context):
    app = FastAPI()
    app.include_router(api_router)

    async def verified():
        return context

    app.dependency_overrides[get_verified_admin] = verified
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


def test_admin_session_revocation_has_one_authoritative_route():
    def flattened(router):
        for route in router.routes:
            child = getattr(route, "original_router", None)
            if child is not None:
                yield from flattened(child)
            else:
                yield route

    matches = [
        route for route in flattened(api_router)
        if getattr(route, "path", "").endswith("/admin/security/sessions/{session_id}")
        and "DELETE" in getattr(route, "methods", set())
    ]
    assert len(matches) == 1, "A weaker legacy handler must not shadow the MFA/audit route"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fresh", "role", "payload", "expected"),
    [
        (False, "owner", {"reason": "Lost device"}, 403),
        (True, "support", {"reason": "Lost device"}, 403),
        (True, "owner", None, 422),
        (True, "owner", {"reason": "   "}, 422),
        (True, "owner", {"reason": "  x  "}, 422),
    ],
)
async def test_session_revocation_rejects_invalid_authorization_or_reason(fresh, role, payload, expected):
    context, target_id = await actors(fresh=fresh, role=role)
    async with client_for(context) as client:
        kwargs = {} if payload is None else {"json": payload}
        response = await client.request("DELETE", PATH.format(session_id=target_id), **kwargs)
    assert response.status_code == expected, response.text
    async with SessionFactory() as session:
        target = await session.get(AdminSession, target_id)
        assert target.revoked_at is None
        assert target.revoke_reason is None


@pytest.mark.asyncio
async def test_authorized_session_revocation_retains_normalized_reason_and_audit():
    context, target_id = await actors()
    async with client_for(context) as client:
        response = await client.request(
            "DELETE", PATH.format(session_id=target_id), json={"reason": "  Lost device  "},
        )
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(target_id), "status": "revoked", "revoked": True}
    async with SessionFactory() as session:
        target = await session.get(AdminSession, target_id)
        audit = await session.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "admin.session.revoked",
                AdminAuditLog.resource_id == str(target_id),
            )
        )
        assert target.revoked_at is not None
        assert target.revoke_reason == "Lost device"
        assert audit is not None
        assert audit.reason == "Lost device"
        assert audit.admin_id == context.account.id
        assert audit.session_id == context.session.id
