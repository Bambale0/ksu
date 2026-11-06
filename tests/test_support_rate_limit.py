from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.v1 import admin_operations, support
from app.core.config import Settings, settings
from app.core.telegram_browser_auth import build_browser_init_data
from app.db.admin_models import SupportOutbox
from app.db.models import AdminAccount, AdminSession, SupportMessage, SupportTicket, User
from app.db.session import SessionFactory
from app.main import resource_policy_error
from app.services.abuse_protection import ResourcePolicyError
from app.services.support import SupportConversationService

BOT_TOKEN = "123456:isolated-support-rate-test-token"


@pytest.fixture(autouse=True)
def configured_support(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "admin_security_key", "isolated-support-rate-key-20261106")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "abuse_fail_closed", True)
    # Inject route configuration so the pre-fix HTTP RED is about missing
    # admission, rather than failing fixture setup on the not-yet-added field.
    monkeypatch.setattr(support, "settings", SimpleNamespace(
        support_message_rate_limit_per_minute=3, support_telegram_url="",
    ))


@pytest.fixture
def notices(monkeypatch):
    spy = AsyncMock(wraps=SupportConversationService.notify_operators)
    monkeypatch.setattr(SupportConversationService, "notify_operators", spy)
    return spy


async def actors():
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        customer, other, operator = [
            User(
                telegram_id=9_400_000_000_000 + uuid.uuid4().int % 100_000_000_000,
                first_name="Support rate regression", is_active=True,
            )
            for _ in range(3)
        ]
        session.add_all([customer, other, operator])
        await session.flush()
        account = AdminAccount(
            user_id=operator.id, role="support", is_active=True,
            permission_overrides={}, mfa_enabled=True,
        )
        session.add(account)
        await session.flush()
        record = AdminSession(
            admin_id=account.id, token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1), mfa_verified=True, session_version=1,
        )
        session.add(record)
        await session.commit()
    return customer, other, AdminContext(account=account, session=record, user=operator)


def signed_headers(user):
    return {"X-Telegram-Init-Data": build_browser_init_data(
        {"id": user.telegram_id, "first_name": user.first_name}, BOT_TOKEN,
    )}


async def ticket_for(user, *, status="open"):
    async with SessionFactory() as session:
        ticket = SupportTicket(user_id=user.id, topic="Rate regression", status=status)
        session.add(ticket)
        await session.commit()
        return ticket


async def counts(user):
    async with SessionFactory() as session:
        tickets = await session.scalar(select(func.count()).select_from(SupportTicket).where(
            SupportTicket.user_id == user.id,
        ))
        messages = await session.scalar(select(func.count()).select_from(SupportMessage).join(
            SupportTicket, SupportTicket.id == SupportMessage.ticket_id,
        ).where(SupportTicket.user_id == user.id, SupportMessage.is_admin.is_(False)))
    return tickets, messages


@asynccontextmanager
async def client_for(context, *, backend=None):
    app = FastAPI()
    app.include_router(support.router, prefix="/api/v1")
    app.include_router(admin_operations.router, prefix="/api/v1")
    app.add_exception_handler(ResourcePolicyError, resource_policy_error)

    async def verified():
        return context

    app.dependency_overrides[get_verified_admin] = verified
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = backend if backend is not None else redis
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, redis
    finally:
        await redis.aclose()


def assert_limited(response, *, max_wait=60):
    assert response.status_code == 429, response.text
    payload = response.json()
    assert payload["code"] == "resource_limit_exceeded"
    assert 1 <= int(response.headers["Retry-After"]) <= max_wait
    assert payload["retry_after"] == int(response.headers["Retry-After"])


@pytest.mark.asyncio
async def test_create_and_reply_share_one_user_budget_without_blocking_reads_or_other_users(notices):
    customer, other, context = await actors()
    async with client_for(context) as (client, _):
        headers = signed_headers(customer)
        first = await client.post("/api/v1/support/tickets", headers=headers, json={
            "topic": "Payment", "message": "First message",
        })
        second = await client.post("/api/v1/support/tickets", headers=headers, json={
            "topic": "Video", "message": "Second message",
        })
        assert first.status_code == second.status_code == 201
        ticket_id = first.json()["id"]
        reply = await client.post(f"/api/v1/support/tickets/{ticket_id}/messages", headers=headers, json={
            "message": "Third message",
        })
        assert reply.status_code == 201
        for path, body in [
            (f"/api/v1/support/tickets/{ticket_id}/messages", {"message": "Over limit reply"}),
            ("/api/v1/support/tickets", {"topic": "More", "message": "Over limit create"}),
        ]:
            assert_limited(await client.post(path, headers=headers, json=body))
        assert await counts(customer) == (2, 3)
        assert notices.await_count == 3
        assert (await client.get("/api/v1/support/tickets", headers=headers)).status_code == 200
        assert (await client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)).status_code == 200
        assert (await client.post(f"/api/v1/support/tickets/{ticket_id}/close", headers=headers)).status_code == 200
        assert (await client.post(f"/api/v1/support/tickets/{ticket_id}/reopen", headers=headers)).status_code == 200
        another = await client.post("/api/v1/support/tickets", headers=signed_headers(other), json={
            "topic": "Separate user", "message": "Own budget",
        })
        assert another.status_code == 201
        assert notices.await_count == 4


@pytest.mark.asyncio
async def test_concurrent_mixed_create_and_reply_cannot_exceed_atomic_budget(notices):
    customer, _, context = await actors()
    existing = [await ticket_for(customer), await ticket_for(customer)]
    async with client_for(context) as (client, redis):
        headers = signed_headers(customer)
        requests = [
            client.post(
                "/api/v1/support/tickets" if index % 2 == 0
                else f"/api/v1/support/tickets/{existing[(index // 2) % len(existing)].id}/messages",
                headers=headers,
                json={"topic": "Concurrent", "message": f"Message {index}"} if index % 2 == 0
                else {"message": f"Message {index}"},
            )
            for index in range(20)
        ]
        results = await asyncio.gather(*requests)
        accepted = [response for response in results if response.status_code == 201]
        assert len(accepted) == 3, [response.status_code for response in results]
        for response in results:
            if response.status_code != 201:
                assert_limited(response)
        created = sum("topic" in response.json() for response in accepted)
        assert await counts(customer) == (2 + created, 3)
        assert notices.await_count == 3
        assert 1 <= await redis.ttl(f"abuse:support:user:{customer.id}") <= 60


@pytest.mark.asyncio
async def test_invalid_unauthorized_foreign_and_closed_requests_do_not_spend_quota(notices):
    customer, other, context = await actors()
    own = await ticket_for(customer)
    closed = await ticket_for(customer, status="closed")
    foreign = await ticket_for(other)
    support.settings.support_message_rate_limit_per_minute = 1
    async with client_for(context) as (client, redis):
        headers = signed_headers(customer)
        cases = [
            ("/api/v1/support/tickets", {"topic": " ", "message": "text"}, headers, 422),
            ("/api/v1/support/tickets", {"topic": "topic", "message": " "}, headers, 422),
            ("/api/v1/support/tickets", {"topic": "topic", "message": "x" * 8001}, headers, 422),
            ("/api/v1/support/tickets", {"topic": "topic", "message": "text"}, {}, 401),
            (f"/api/v1/support/tickets/{uuid.uuid4()}/messages", {"message": "text"}, headers, 404),
            (f"/api/v1/support/tickets/{foreign.id}/messages", {"message": "text"}, headers, 404),
            (f"/api/v1/support/tickets/{closed.id}/messages", {"message": "text"}, headers, 409),
            (f"/api/v1/support/tickets/{own.id}/messages", {"message": " "}, headers, 422),
        ]
        for path, body, request_headers, expected in cases:
            response = await client.post(path, headers=request_headers, json=body)
            assert response.status_code == expected, response.text
        assert await redis.get(f"abuse:support:user:{customer.id}") is None
        assert await counts(customer) == (2, 0)
        assert notices.await_count == 0
        accepted = await client.post(f"/api/v1/support/tickets/{own.id}/messages", headers=headers, json={
            "message": "Valid message",
        })
        assert accepted.status_code == 201
        assert_limited(await client.post("/api/v1/support/tickets", headers=headers, json={
            "topic": "Another", "message": "Over the shared quota",
        }))


@pytest.mark.asyncio
async def test_retry_after_uses_existing_ttl_and_expiry_restores_admission(notices):
    customer, _, context = await actors()
    support.settings.support_message_rate_limit_per_minute = 1
    async with client_for(context) as (client, redis):
        headers = signed_headers(customer)
        body = {"topic": "Window", "message": "One"}
        assert (await client.post("/api/v1/support/tickets", headers=headers, json=body)).status_code == 201
        key = f"abuse:support:user:{customer.id}"
        await redis.expire(key, 11)
        assert_limited(await client.post("/api/v1/support/tickets", headers=headers, json=body), max_wait=11)
        assert 1 <= await redis.ttl(key) <= 11
        # Expire the real Redis key instead of sleeping or changing the policy clock.
        await redis.expire(key, 0)
        assert (await client.post("/api/v1/support/tickets", headers=headers, json=body)).status_code == 201
        assert await counts(customer) == (2, 2)
        assert notices.await_count == 2


class BrokenRedis:
    async def eval(self, *_args, **_kwargs):
        raise RedisError("Synthetic rate backend unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "reply"])
async def test_unavailable_redis_fails_closed_before_support_persistence_or_notification(action, notices):
    customer, _, context = await actors()
    ticket = await ticket_for(customer)
    async with client_for(context, backend=BrokenRedis()) as (client, _):
        path = "/api/v1/support/tickets" if action == "create" else f"/api/v1/support/tickets/{ticket.id}/messages"
        body = {"topic": "Unavailable", "message": "Do not persist"} if action == "create" else {"message": "Do not persist"}
        response = await client.post(path, headers=signed_headers(customer), json=body)
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "protection_backend_unavailable"
        assert int(response.headers["Retry-After"]) > 0
        assert await counts(customer) == (1, 0)
        assert notices.await_count == 0


@pytest.mark.asyncio
async def test_operator_reply_remains_available_after_customer_quota_exhaustion(notices):
    customer, _, context = await actors()
    support.settings.support_message_rate_limit_per_minute = 1
    async with client_for(context) as (client, redis):
        headers = signed_headers(customer)
        created = await client.post("/api/v1/support/tickets", headers=headers, json={
            "topic": "Operator reply", "message": "Customer message",
        })
        assert created.status_code == 201
        ticket_id = created.json()["id"]
        assert_limited(await client.post(f"/api/v1/support/tickets/{ticket_id}/messages", headers=headers, json={
            "message": "Over the quota",
        }))
        await redis.set(f"abuse:support:user:{context.user.id}", "999", ex=60)
        reply = await client.post(
            f"/api/v1/admin/support/tickets/{ticket_id}/messages",
            headers={"Idempotency-Key": str(uuid.uuid4()), "X-Admin-Confirm": "true"},
            json={"body": "Operator can still resolve the issue"},
        )
        assert reply.status_code == 201, reply.text
        assert reply.json()["delivery_status"] == "pending"
        assert notices.await_count == 1
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count()).select_from(SupportOutbox).where(
                SupportOutbox.ticket_id == uuid.UUID(ticket_id),
            )) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["quota-zero", "globally-disabled", "fail-open"])
async def test_explicit_existing_abuse_policy_switches_are_respected(policy, notices, monkeypatch):
    customer, _, context = await actors()
    if policy == "quota-zero":
        support.settings.support_message_rate_limit_per_minute = 0
    elif policy == "globally-disabled":
        monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    else:
        monkeypatch.setattr(settings, "abuse_fail_closed", False)
    async with client_for(context, backend=BrokenRedis()) as (client, _):
        response = await client.post("/api/v1/support/tickets", headers=signed_headers(customer), json={
            "topic": "Explicit policy", "message": "Accepted by configured policy",
        })
        assert response.status_code == 201, response.text
        assert await counts(customer) == (1, 1)
        assert notices.await_count == 1


def test_support_quota_setting_is_independent_typed_and_nonnegative():
    field = Settings.model_fields["support_message_rate_limit_per_minute"]
    assert field.annotation is int
    assert field.default == 10
    with pytest.raises(ValidationError):
        Settings(_env_file=None, support_message_rate_limit_per_minute=-1)
