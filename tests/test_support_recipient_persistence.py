from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from aiogram.types import User as TelegramUser
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.deps import get_current_user
from app.api.v1 import admin_accounts, notifications, support
from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, AdminSession, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.admin_security import AdminAuthService, hash_admin_token
from app.services.notification_events import register_notification_events
from app.workers import notifications as notification_worker

SETTING_KEY = "support_incoming_recipients"


@pytest_asyncio.fixture(autouse=True)
async def recipient_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "recipient-regression-key-at-least-32-characters")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    monkeypatch.setattr(settings, "admin_require_mfa", True)
    async with SessionFactory() as session:
        await session.execute(delete(AdminRuntimeSetting).where(AdminRuntimeSetting.key == SETTING_KEY))
        await session.commit()
    yield
    async with SessionFactory() as session:
        await session.execute(delete(AdminRuntimeSetting).where(AdminRuntimeSetting.key == SETTING_KEY))
        await session.commit()


def _telegram_id() -> int:
    return 7_000_000_000_000 + uuid.uuid4().int % 1_000_000_000_000


async def _actors():
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        owner = User(telegram_id=_telegram_id(), first_name="Recipient owner")
        operator = User(telegram_id=_telegram_id(), first_name="Selected operator")
        customer = User(telegram_id=_telegram_id(), first_name="Customer")
        candidate = User(telegram_id=_telegram_id(), first_name="Registered candidate")
        unrelated = User(telegram_id=_telegram_id(), first_name="Unselected administrator")
        session.add_all([owner, operator, customer, candidate, unrelated])
        await session.flush()
        owner_account = AdminAccount(user_id=owner.id, role="owner", is_active=True, mfa_enabled=True)
        operator_account = AdminAccount(
            user_id=operator.id, role="support", is_active=True, mfa_enabled=True,
        )
        unrelated_account = AdminAccount(
            user_id=unrelated.id, role="admin", is_active=True, mfa_enabled=True,
        )
        session.add_all([owner_account, operator_account, unrelated_account])
        await session.flush()
        contexts = []
        tokens = []
        for user, account in ((owner, owner_account), (operator, operator_account)):
            token = uuid.uuid4().hex + uuid.uuid4().hex
            record = AdminSession(
                admin_id=account.id, token_hash=hash_admin_token(token),
                created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
                idle_expires_at=now + timedelta(hours=1), step_up_until=now + timedelta(minutes=5),
                mfa_verified=True, session_version=account.session_version,
            )
            session.add(record)
            await session.flush()
            contexts.append(AdminContext(account=account, session=record, user=user))
            tokens.append(token)
        await session.commit()
        return SimpleNamespace(
            owner=contexts[0], operator=contexts[1], customer=customer,
            candidate=candidate, unrelated=unrelated, owner_token=tokens[0],
        )


@asynccontextmanager
async def _client(context: AdminContext, user: User, *, token: str | None = None):
    from app.main import resource_policy_error
    from app.services.abuse_protection import ResourcePolicyError

    register_notification_events()
    app = FastAPI()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    app.add_exception_handler(ResourcePolicyError, resource_policy_error)
    for router in (admin_accounts.router, support.router, notifications.router):
        app.include_router(router, prefix="/api/v1")

    async def verified():
        return context

    async def current_user():
        return user

    if token is None:
        app.dependency_overrides[get_verified_admin] = verified
    app.dependency_overrides[get_current_user] = current_user
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers,
        ) as client:
            yield client
    finally:
        await redis.aclose()


async def _policy():
    async with SessionFactory() as session:
        row = await session.get(AdminRuntimeSetting, SETTING_KEY)
        return dict(row.value) if row is not None else None


async def _notices(ticket_id: str):
    async with SessionFactory() as session:
        return list((await session.scalars(select(Notification).where(
            Notification.kind == "support_incoming",
            Notification.body.contains(ticket_id),
        ))).all())


async def _incoming(client: httpx.AsyncClient, topic: str = "Recipient regression") -> str:
    response = await client.post(
        "/api/v1/support/tickets", json={"topic": topic, "message": "Private customer text"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _subscribe(client: httpx.AsyncClient, admin_id: uuid.UUID, enabled: bool):
    return await client.patch(f"/api/v1/admin/admins/{admin_id}", json={
        "support_notifications": enabled, "reason": "Explicit recipient assignment",
    })


async def _startup(monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "bot_token", "")
    monkeypatch.setattr(main.FeedStaticStorage, "ensure_root", lambda: None)
    monkeypatch.setattr(main.ReferenceStaticStorage, "ensure_root", lambda: None)
    monkeypatch.setattr(main.AdminPricingService, "hydrate_runtime", AsyncMock())
    async with main.lifespan(FastAPI()):
        pass


@pytest.mark.asyncio
async def test_owner_created_operator_receives_notices_without_bootstrap():
    actors = await _actors()
    async with _client(actors.owner, actors.customer, token=actors.owner_token) as client:
        created = await client.post("/api/v1/admin/admins", json={
            "telegram_id": actors.candidate.telegram_id, "role": "support",
            "support_notifications": True,
        })
        assert created.status_code == 201, created.text
        ticket_id = await _incoming(client)
        notices = await _notices(ticket_id)
        assert [item.user_id for item in notices] == [actors.candidate.id]
        assert created.json()["support_notifications"] is True
        assert created.json()["support_notifications_effective"] is True
        listed = await client.get("/api/v1/admin/admins")
        assert listed.status_code == 200
        assert listed.json()["support_notifications_configured"] is True
        selected = {item["id"] for item in listed.json()["items"] if item["support_notifications"]}
        assert selected == {created.json()["id"]}
        # A legacy edit must not silently opt the selected recipient out.
        updated = await client.patch(f"/api/v1/admin/admins/{created.json()['id']}", json={
            "role": "support", "reason": "Legacy client updates administrator",
        })
        assert updated.status_code == 200
        assert updated.json()["support_notifications"] is True

    async with _client(actors.owner, actors.candidate) as client:
        inbox = await client.get("/api/v1/notifications")
        assert str(notices[0].id) in {item["id"] for item in inbox.json()["items"]}
    assert (await _policy())["admin_ids"] == [created.json()["id"]]


@pytest.mark.asyncio
async def test_startup_import_survives_clearing_bootstrap(monkeypatch):
    actors = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(actors.operator.user.telegram_id))
    await _startup(monkeypatch)
    policy = await _policy()
    assert policy is not None
    assert policy["admin_ids"] == [str(actors.operator.account.id)]
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    await _startup(monkeypatch)
    async with _client(actors.owner, actors.customer) as client:
        ticket_id = await _incoming(client)
    notices = await _notices(ticket_id)
    assert [item.user_id for item in notices] == [actors.operator.user.id]
    async with SessionFactory() as session:
        delivery = await session.scalar(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notices[0].id,
        ))
        delivery.status = "sending"
        await session.commit()
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=83)

    await notification_worker._process_delivery(SimpleNamespace(send_message=send_message), delivery.id)
    assert [item["chat_id"] for item in calls] == [actors.operator.user.telegram_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("bootstrap_path", ["admin_login", "mini_app"])
async def test_empty_startup_does_not_block_first_owner_enrollment(monkeypatch, bootstrap_path):
    from app.services.inline_admin import ensure_bootstrap_admin
    from app.services.support import SupportConversationService

    actors = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(actors.candidate.telegram_id))
    await _startup(monkeypatch)
    assert await _policy() is None
    async with SessionFactory() as session:
        if bootstrap_path == "admin_login":
            account = await AdminAuthService.get_or_bootstrap_admin(session, TelegramUser(
                id=actors.candidate.telegram_id, first_name="New owner", is_bot=False,
            ))
        else:
            user = await session.get(User, actors.candidate.id)
            account = await ensure_bootstrap_admin(session, user)
        assert account is not None
        await session.commit()
    policy = await _policy()
    assert policy is not None
    assert policy["admin_ids"] == [str(account.id)]
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    async with SessionFactory() as session:
        assert await SupportConversationService.authorized_operator(
            session, actors.candidate.id, lock=True,
        )


@pytest.mark.asyncio
async def test_explicit_empty_selection_wins_over_bootstrap_and_restart(monkeypatch):
    actors = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(actors.owner.user.telegram_id))
    async with _client(actors.owner, actors.customer) as client:
        response = await _subscribe(client, actors.owner.account.id, False)
        assert response.status_code == 200
        ticket_id = await _incoming(client)
        assert await _notices(ticket_id) == []
    policy = await _policy()
    assert policy is not None and policy["admin_ids"] == []
    await _startup(monkeypatch)
    assert (await _policy())["admin_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ineligible", ["user_inactive", "admin_inactive", "support_denied"])
async def test_owner_cannot_subscribe_an_ineligible_account(ineligible):
    actors = await _actors()
    async with SessionFactory() as session:
        user = await session.get(User, actors.operator.user.id)
        account = await session.get(AdminAccount, actors.operator.account.id)
        if ineligible == "user_inactive":
            user.is_active = False
        elif ineligible == "admin_inactive":
            account.is_active = False
        else:
            account.permission_overrides = {"deny": ["support.read"]}
        await session.commit()
    async with _client(actors.owner, actors.customer) as client:
        response = await _subscribe(client, actors.operator.account.id, True)
        assert response.status_code == 422
    policy = await _policy()
    assert policy is None or str(actors.operator.account.id) not in policy["admin_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["non_owner", "stale_mfa"])
async def test_recipient_assignment_preserves_owner_and_fresh_mfa_gates(denial):
    actors = await _actors()
    context = actors.owner
    if denial == "non_owner":
        context = actors.operator
        context.account.permission_overrides = {"allow": ["admins.manage"]}
    else:
        context.session.step_up_until = datetime.now(UTC) - timedelta(seconds=1)
    async with _client(context, actors.customer) as client:
        response = await _subscribe(client, actors.operator.account.id, True)
        assert response.status_code == 403
    assert await _policy() is None


@pytest.mark.asyncio
async def test_concurrent_explicit_assignments_do_not_lose_an_operator():
    actors = await _actors()
    async with _client(actors.owner, actors.customer) as client:
        responses = await asyncio.gather(
            _subscribe(client, actors.operator.account.id, True),
            _subscribe(client, actors.owner.account.id, True),
        )
        assert [response.status_code for response in responses] == [200, 200]
    policy = await _policy()
    assert policy is not None
    assert set(policy["admin_ids"]) == {str(actors.operator.account.id), str(actors.owner.account.id)}


@pytest.mark.asyncio
async def test_malformed_persisted_membership_fails_closed_even_with_bootstrap(monkeypatch):
    actors = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(actors.owner.user.telegram_id))
    async with SessionFactory() as session:
        session.add(AdminRuntimeSetting(
            key=SETTING_KEY, value={"revision": 1, "admin_ids": ["not-a-uuid"]},
            updated_by_admin_id=actors.owner.account.id,
        ))
        await session.commit()
    async with _client(actors.owner, actors.customer) as client:
        ticket_id = await _incoming(client)
    assert await _notices(ticket_id) == []


@pytest.mark.asyncio
async def test_recipient_removal_serializes_with_delivery_and_suppresses_next_notice(monkeypatch):
    actors = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(actors.operator.user.telegram_id))
    async with _client(actors.owner, actors.customer, token=actors.owner_token) as client:
        selected = await _subscribe(client, actors.operator.account.id, True)
        assert selected.status_code == 200
        first_ticket = await _incoming(client, "First in flight")
        next_ticket = await _incoming(client, "Pending next")
        notices = [*(await _notices(first_ticket)), *(await _notices(next_ticket))]
        assert len(notices) == 2
        async with SessionFactory() as session:
            deliveries = list((await session.scalars(select(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_([item.id for item in notices]),
            ).order_by(NotificationDelivery.created_at, NotificationDelivery.id))).all())
            for delivery in deliveries:
                delivery.status = "sending"
            await session.commit()
        sending = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def send_message(**kwargs):
            calls.append(kwargs)
            sending.set()
            await release.wait()
            return SimpleNamespace(message_id=84)

        bot = SimpleNamespace(send_message=send_message)
        send_task = asyncio.create_task(notification_worker._process_delivery(bot, deliveries[0].id))
        await asyncio.wait_for(sending.wait(), timeout=5)
        remove_task = asyncio.create_task(_subscribe(client, actors.operator.account.id, False))
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(remove_task), timeout=0.2)
        finally:
            release.set()
            _, removed = await asyncio.wait_for(asyncio.gather(send_task, remove_task), timeout=5)
        assert removed.status_code == 200
        assert removed.json()["support_notifications"] is False
        await notification_worker._process_delivery(bot, deliveries[1].id)
        assert len(calls) == 1
        async with SessionFactory() as session:
            remaining = await session.get(NotificationDelivery, deliveries[1].id)
            assert remaining.status == "suppressed"
    async with _client(actors.owner, actors.operator.user) as client:
        inbox = await client.get("/api/v1/notifications")
        assert not {str(item.id) for item in notices} & {item["id"] for item in inbox.json()["items"]}


@pytest.mark.asyncio
async def test_selected_operators_can_open_customer_tickets_concurrently(monkeypatch):
    from app.services.support import SupportConversationService

    actors = await _actors()
    async with _client(actors.owner, actors.customer) as manager:
        assert (await _subscribe(manager, actors.owner.account.id, True)).status_code == 200
        assert (await _subscribe(manager, actors.operator.account.id, True)).status_code == 200

    original = SupportConversationService.notify_operators
    both_messages_flushed = asyncio.Event()
    arrived = 0

    async def notify_after_both_messages_flush(*args, **kwargs):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_messages_flushed.set()
        await asyncio.wait_for(both_messages_flushed.wait(), timeout=5)
        await original(*args, **kwargs)

    monkeypatch.setattr(
        SupportConversationService, "notify_operators", staticmethod(notify_after_both_messages_flush),
    )
    # Each real insert already holds its own customer User FK KEY SHARE lock at the barrier.
    async with (
        _client(actors.owner, actors.owner.user) as first,
        _client(actors.owner, actors.operator.user) as second,
    ):
        results = await asyncio.wait_for(asyncio.gather(
            first.post("/api/v1/support/tickets", json={"topic": "Operator A", "message": "Own question A"}),
            second.post("/api/v1/support/tickets", json={"topic": "Operator B", "message": "Own question B"}),
            return_exceptions=True,
        ), timeout=8)
    statuses = [item.status_code if isinstance(item, httpx.Response) else type(item).__name__ for item in results]
    assert statuses == [201, 201]
    for response in results:
        notices = await _notices(response.json()["id"])
        assert {item.user_id for item in notices} == {actors.owner.user.id, actors.operator.user.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("account_change", [{"is_active": False}, {"role": "finance"}])
async def test_existing_subscription_does_not_block_account_privilege_changes(account_change):
    actors = await _actors()
    async with _client(actors.owner, actors.customer, token=actors.owner_token) as client:
        assert (await _subscribe(client, actors.operator.account.id, True)).status_code == 200
        response = await client.patch(f"/api/v1/admin/admins/{actors.operator.account.id}", json={
            **account_change,
            "support_notifications": True,
            "reason": "Owner changes access while preserving notification preference",
        })
        assert response.status_code == 200, response.text
        assert response.json()["support_notifications"] is True
        assert response.json()["support_notifications_effective"] is False
        ticket_id = await _incoming(client, "After access revocation")
        assert await _notices(ticket_id) == []
    assert str(actors.operator.account.id) in (await _policy())["admin_ids"]
