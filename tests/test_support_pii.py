from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import delete

from app.api.v1 import admin_control, admin_operations, admin_users
from app.core.config import settings
from app.db.models import AdminAccount, AdminAuditLog, AdminSession, SupportMessage, SupportTicket, User
from app.db.session import SessionFactory
from app.services.admin_security import hash_admin_token

PERMISSIONS = [
    pytest.param(("support", {}, False), id="support"),
    pytest.param(("moderator", {}, False), id="moderator"),
    pytest.param(("auditor", {}, False), id="auditor"),
    pytest.param(("admin", {"deny": ["users.pii"]}, False), id="admin-explicit-deny"),
    pytest.param(("support", {"allow": ["users.pii"]}, True), id="support-explicit-allow"),
    pytest.param(("admin", {}, True), id="admin"),
]
SUPPORT_PATHS = ["/api/v1/admin/support/tickets", "/api/v1/admin/control/tickets"]
USER_PATHS = ["/api/v1/admin/users", "/api/v1/admin/control/users"]


def _telegram_id():
    return 7_600_000_000_000 + uuid.uuid4().int % 100_000_000_000


@pytest_asyncio.fixture
async def pii_actor(request, monkeypatch):
    role, overrides, can_pii = request.param
    monkeypatch.setattr(settings, "admin_security_key", "support-pii-regression-key-at-least-32-characters")
    monkeypatch.setattr(settings, "admin_require_mfa", True)
    marker = uuid.uuid4().hex
    token = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        operator = User(telegram_id=_telegram_id(), first_name="PII boundary operator")
        customer = User(
            telegram_id=_telegram_id(), username=f"private_{marker}",
            first_name=f"PrivateFirst{marker}", last_name=f"PrivateLast{marker}",
        )
        session.add_all([operator, customer])
        await session.flush()
        admin = AdminAccount(
            user_id=operator.id, role=role, permission_overrides=overrides,
            is_active=True, mfa_enabled=True,
        )
        ticket = SupportTicket(
            user_id=customer.id, topic=f"Billing question {uuid.uuid4().hex}", status="open",
        )
        session.add_all([admin, ticket])
        await session.flush()
        admin_session = AdminSession(
            admin_id=admin.id, token_hash=hash_admin_token(token),
            created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1), mfa_verified=True,
            session_version=admin.session_version,
        )
        message = SupportMessage(
            ticket_id=ticket.id, user_id=customer.id, is_admin=False,
            body="Customer text remains available to authorized support readers",
        )
        session.add_all([admin_session, message])
        await session.commit()
    try:
        yield SimpleNamespace(
            admin=admin, customer=customer, operator=operator, ticket=ticket,
            message=message, token=token, can_pii=can_pii,
        )
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
            await session.execute(delete(SupportTicket).where(SupportTicket.id == ticket.id))
            await session.execute(delete(AdminAuditLog).where(AdminAuditLog.admin_id == admin.id))
            await session.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
            await session.execute(delete(AdminAccount).where(AdminAccount.id == admin.id))
            await session.execute(delete(User).where(User.id.in_([operator.id, customer.id])))
            await session.commit()


@asynccontextmanager
async def _client(actor):
    app = FastAPI()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    for router in (admin_operations.router, admin_control.router, admin_users.router):
        app.include_router(router, prefix="/api/v1")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": f"Bearer {actor.token}"},
        ) as client:
            yield client
    finally:
        await redis.aclose()


def _assert_identity(view, actor):
    user = actor.customer
    assert view["id"] == str(user.id)
    expected = (
        {
            "telegram_id": user.telegram_id, "username": user.username,
            "first_name": user.first_name, "last_name": user.last_name,
        }
        if actor.can_pii else
        {
            "telegram_id": f"***{str(user.telegram_id)[-4:]}", "username": None,
            "first_name": "[restricted]", "last_name": None,
        }
    )
    assert {key: view[key] for key in expected} == expected


def _private_queries(actor):
    return [
        str(actor.customer.telegram_id), actor.customer.username,
        actor.customer.first_name, actor.customer.last_name,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("pii_actor", PERMISSIONS, indirect=True)
@pytest.mark.parametrize("path", SUPPORT_PATHS)
async def test_support_list_detail_and_search_respect_effective_pii_permission(pii_actor, path):
    actor = pii_actor
    async with _client(actor) as client:
        listed = await client.get(path, params={"q": str(actor.ticket.id), "limit": 1})
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        item = listed.json()["items"][0]
        assert item["user_id"] == str(actor.customer.id)
        _assert_identity(item["user"], actor)

        detail = await client.get(f"{path}/{actor.ticket.id}")
        assert detail.status_code == 200, detail.text
        _assert_identity(detail.json()["user"], actor)
        assert detail.json()["messages"][0]["body"] == actor.message.body

        for query in _private_queries(actor):
            response = await client.get(path, params={"q": query, "limit": 1})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["total"] == int(actor.can_pii), "Private search revealed a customer match"
            assert [item["id"] for item in data["items"]] == (
                [str(actor.ticket.id)] if actor.can_pii else []
            )
            assert data["has_more"] is False

        for query in (str(actor.customer.id), actor.ticket.topic):
            response = await client.get(path, params={"q": query, "status": "open"})
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert [item["id"] for item in response.json()["items"]] == [str(actor.ticket.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("pii_actor", PERMISSIONS, indirect=True)
@pytest.mark.parametrize("path", USER_PATHS)
async def test_user_search_cannot_infer_hidden_identity_and_uuid_remains_available(pii_actor, path):
    actor = pii_actor
    async with _client(actor) as client:
        for query in _private_queries(actor):
            response = await client.get(path, params={"q": query, "limit": 1})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["total"] == int(actor.can_pii), "Private search revealed a hidden user"
            assert [item["id"] for item in data["items"]] == (
                [str(actor.customer.id)] if actor.can_pii else []
            )

        response = await client.get(path, params={
            "q": str(actor.customer.id), "is_active": "true", "limit": 1,
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 1
        _assert_identity(data["items"][0], actor)
        detail = await client.get(f"{path}/{actor.customer.id}")
        assert detail.status_code == 200, detail.text
        _assert_identity(detail.json(), actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("pii_actor", [("finance", {}, True)], indirect=True)
@pytest.mark.parametrize("path", SUPPORT_PATHS)
async def test_pii_permission_alone_does_not_grant_support_access(pii_actor, path):
    async with _client(pii_actor) as client:
        listed = await client.get(path, params={"q": str(pii_actor.customer.telegram_id)})
        detail = await client.get(f"{path}/{pii_actor.ticket.id}")
    assert listed.status_code == 403
    assert detail.status_code == 403
