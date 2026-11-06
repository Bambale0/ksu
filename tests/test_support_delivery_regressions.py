from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.deps import get_current_user
from app.api.v1 import admin_control, admin_operations, notifications, support
from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting, SupportOutbox
from app.db.models import AdminAccount, AdminSession, Notification, SupportMessage, SupportTicket, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.notification_events import register_notification_events
from app.services.notifications import NotificationDeliveryService
from app.services.support_recipient_config import SUPPORT_RECIPIENT_SETTING_KEY
from app.workers import admin_support as support_worker
from app.workers import notifications as notification_worker

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def support_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "support-regression-test-key-32-characters-minimum")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    # Each case owns its explicit operator scope; fixtures must not retain a prior case's policy.
    async with SessionFactory() as session:
        await session.execute(delete(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == SUPPORT_RECIPIENT_SETTING_KEY,
        ))
        await session.commit()
    yield
    async with SessionFactory() as session:
        await session.execute(delete(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == SUPPORT_RECIPIENT_SETTING_KEY,
        ))
        await session.commit()


def _telegram_id() -> int:
    return 8_000_000_000_000 + uuid.uuid4().int % 1_000_000_000_000


async def _actors():
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        operator = User(telegram_id=_telegram_id(), first_name="Support operator")
        customer = User(
            telegram_id=_telegram_id(), first_name="Support customer",
            username=f"support_{uuid.uuid4().hex[:12]}",
        )
        session.add_all([operator, customer])
        await session.flush()
        account = AdminAccount(
            user_id=operator.id, role="support", permission_overrides={},
            is_active=True, mfa_enabled=True,
        )
        session.add(account)
        await session.flush()
        admin_session = AdminSession(
            admin_id=account.id, token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1), mfa_verified=True, session_version=1,
        )
        session.add(admin_session)
        await session.commit()
        return AdminContext(account=account, session=admin_session, user=operator), customer


@asynccontextmanager
async def _client(context: AdminContext, customer: User):
    from app.main import resource_policy_error
    from app.services.abuse_protection import ResourcePolicyError

    register_notification_events()
    app = FastAPI()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    app.add_exception_handler(ResourcePolicyError, resource_policy_error)
    for router in (support.router, admin_operations.router, admin_control.router, notifications.router):
        app.include_router(router, prefix="/api/v1")

    async def verified():
        return context

    async def current_user():
        return customer

    app.dependency_overrides[get_verified_admin] = verified
    app.dependency_overrides[get_current_user] = current_user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await redis.aclose()


async def _ticket(customer: User, *, topic: str = "Support regression") -> SupportTicket:
    async with SessionFactory() as session:
        item = SupportTicket(user_id=customer.id, topic=topic)
        session.add(item)
        await session.commit()
        return item


def _write_headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4()), "X-Admin-Confirm": "true"}


async def test_incoming_messages_notify_only_configured_authorized_operators(monkeypatch):
    context, customer = await _actors()
    other, _ = await _actors()
    denied, _ = await _actors()
    inactive, _ = await _actors()
    async with SessionFactory() as session:
        denied_account = await session.get(AdminAccount, denied.account.id)
        denied_account.permission_overrides = {"deny": ["support.read"]}
        inactive_user = await session.get(User, inactive.user.id)
        inactive_user.is_active = False
        await session.commit()
    monkeypatch.setattr(
        settings, "admin_bootstrap_telegram_ids",
        f"{context.user.telegram_id},{denied.user.telegram_id},{inactive.user.telegram_id}",
    )
    async with _client(context, customer) as client:
        response = await client.post("/api/v1/support/tickets", json={
            "topic": "Delivery check", "message": "Private synthetic customer detail",
        })
        assert response.status_code == 201
        ticket_id = response.json()["id"]
        async with SessionFactory() as session:
            notices = (await session.scalars(select(Notification).where(
                Notification.kind == "support_incoming",
                Notification.body.contains(ticket_id),
            ))).all()
            assert [row.user_id for row in notices] == [context.user.id]
            assert "Private synthetic customer detail" not in notices[0].body
            pending = await session.scalar(select(func.count()).select_from(NotificationDelivery).where(
                NotificationDelivery.notification_id == notices[0].id,
                NotificationDelivery.status == "pending",
            ))
            assert pending == 1
        reply = await client.post(f"/api/v1/support/tickets/{ticket_id}/messages", json={"message": "Follow up"})
        assert reply.status_code == 201
        async with SessionFactory() as session:
            notices = (await session.scalars(select(Notification).where(
                Notification.kind == "support_incoming",
                Notification.body.contains(ticket_id),
            ))).all()
            assert len(notices) == 2
            assert {row.user_id for row in notices} == {context.user.id}
            assert other.user.id not in {row.user_id for row in notices}


async def test_user_reply_refreshes_activity_and_legacy_activity_is_visible(monkeypatch):
    context, customer = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    old = datetime.now(UTC) - timedelta(days=7)
    async with SessionFactory() as session:
        older = SupportTicket(
            user_id=customer.id, topic="Older conversation", status="in_progress",
            created_at=old, updated_at=old,
        )
        newer = SupportTicket(
            user_id=customer.id, topic="Newer conversation",
            created_at=old + timedelta(days=1), updated_at=old + timedelta(days=1),
        )
        session.add_all([older, newer])
        await session.commit()
    async with _client(context, customer) as client:
        sent = await client.post(f"/api/v1/support/tickets/{older.id}/messages", json={"message": "Newest activity"})
        assert sent.status_code == 201
        async with SessionFactory() as session:
            stored = await session.get(SupportTicket, older.id)
            assert stored.updated_at > old + timedelta(days=1)
            # Simulate previously saved messages whose ticket timestamp stayed stale.
            stored.updated_at = old
            await session.commit()
        page = await client.get("/api/v1/admin/support/tickets", params={
            "q": customer.username, "limit": 1,
        })
        assert page.status_code == 200
        result = page.json()
        assert result["total"] == 2
        assert result["has_more"] is True
        assert result["items"][0]["id"] == str(older.id)
        assert result["items"][0]["needs_reply"] is True
        assert result["items"][0]["last_message"]["body"] == "Newest activity"
        assert result["items"][0]["user"]["telegram_id"] == customer.telegram_id
        second = await client.get("/api/v1/admin/control/tickets", params={
            "q": customer.username, "limit": 1, "offset": 1,
        })
        assert second.status_code == 200
        assert [item["id"] for item in second.json()["items"]] == [str(newer.id)]
        assert second.json()["has_more"] is False


@pytest.mark.parametrize("surface", ["main", "control"])
async def test_admin_http_reply_is_idempotent_full_text_outbox_with_one_telegram_delivery(surface):
    context, customer = await _actors()
    ticket = await _ticket(customer)
    path = (
        f"/api/v1/admin/support/tickets/{ticket.id}/messages" if surface == "main"
        else f"/api/v1/admin/control/tickets/{ticket.id}/reply"
    )
    headers = _write_headers()
    async with _client(context, customer) as client:
        first = await client.post(path, headers=headers, json={"body": "Полный ответ оператора"})
        assert first.status_code in {200, 201}, first.text
        assert first.json().get("delivery_status") == "pending"
        again = await client.post(path, headers=headers, json={"body": "Полный ответ оператора"})
        assert again.status_code in {200, 201}
        assert again.json()["idempotency_replayed"] is True
        assert again.json()["message_id"] == first.json()["message_id"]
        conflict = await client.post(path, headers=headers, json={"body": "Different reply"})
        assert conflict.status_code == 409
    async with SessionFactory() as session:
        messages = (await session.scalars(select(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id, SupportMessage.is_admin.is_(True),
        ))).all()
        outboxes = (await session.scalars(select(SupportOutbox).where(
            SupportOutbox.ticket_id == ticket.id,
        ))).all()
        assert len(messages) == len(outboxes) == 1
        inbox = (await session.scalars(select(Notification).where(
            Notification.user_id == customer.id, Notification.kind == "support_reply",
        ))).all()
        assert len(inbox) == 1
        generic = await session.scalar(select(func.count()).select_from(NotificationDelivery).where(
            NotificationDelivery.notification_id == inbox[0].id,
        ))
        assert generic == 0


@pytest.mark.parametrize("headers,body,status", [
    ({}, "Reply", 400),
    ({"Idempotency-Key": "support-no-confirm"}, "Reply", 403),
    ({"Idempotency-Key": "support-blank", "X-Admin-Confirm": "true"}, "   ", 422),
])
async def test_main_reply_rejects_missing_safety_headers_or_blank_body(headers, body, status):
    context, customer = await _actors()
    ticket = await _ticket(customer)
    async with _client(context, customer) as client:
        response = await client.post(
            f"/api/v1/admin/support/tickets/{ticket.id}/messages", headers=headers, json={"body": body},
        )
        assert response.status_code == status
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id,
        )) == 0


async def test_admin_history_uses_latest_messages_and_stable_older_cursor():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    foreign = await _ticket(customer, topic="Other ticket")
    base = datetime.now(UTC) - timedelta(days=1)
    async with SessionFactory() as session:
        rows = [SupportMessage(
            id=uuid.uuid4(), ticket_id=ticket.id, user_id=customer.id,
            body=f"message-{index}", created_at=base + timedelta(seconds=index),
        ) for index in range(505)]
        foreign_message = SupportMessage(ticket_id=foreign.id, user_id=customer.id, body="Other")
        session.add_all([*rows, foreign_message])
        await session.commit()
    async with _client(context, customer) as client:
        response = await client.get(f"/api/v1/admin/support/tickets/{ticket.id}", params={"message_limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert [row["body"] for row in data["messages"]] == ["message-502", "message-503", "message-504"]
        assert data["messages_total"] == 505
        assert data["messages_has_more"] is True
        previous = await client.get(f"/api/v1/admin/control/tickets/{ticket.id}", params={
            "message_limit": 3, "before": data["messages_before"],
        })
        assert previous.status_code == 200
        assert [row["body"] for row in previous.json()["messages"]] == ["message-499", "message-500", "message-501"]
        invalid = await client.get(f"/api/v1/admin/support/tickets/{ticket.id}", params={
            "message_limit": 3, "before": str(foreign_message.id),
        })
        assert invalid.status_code == 404


async def test_main_status_reopen_uses_shared_idempotent_transition_rules():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    async with SessionFactory() as session:
        stored = await session.get(SupportTicket, ticket.id)
        stored.status = "closed"
        await session.commit()
    async with _client(context, customer) as client:
        path = f"/api/v1/admin/support/tickets/{ticket.id}/status"
        invalid = await client.patch(path, headers=_write_headers(), json={"status": "in_progress"})
        assert invalid.status_code == 422
        headers = _write_headers()
        reopened = await client.patch(path, headers=headers, json={"status": "open"})
        assert reopened.status_code == 200
        replayed = await client.patch(path, headers=headers, json={"status": "open"})
        assert replayed.status_code == 200
        assert replayed.json()["idempotency_replayed"] is True


async def test_revoked_operator_receives_no_pending_notice_and_cannot_read_it(monkeypatch):
    context, customer = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(context.user.telegram_id))
    async with _client(context, customer) as client:
        created = await client.post("/api/v1/support/tickets", json={"topic": "Restricted", "message": "Private"})
        assert created.status_code == 201
    async with SessionFactory() as session:
        notice = await session.scalar(select(Notification).where(
            Notification.user_id == context.user.id, Notification.kind == "support_incoming",
        ))
        assert notice is not None
        delivery = await session.scalar(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notice.id,
        ))
        delivery.status = "sending"
        delivery.attempts = 1
        account = await session.get(AdminAccount, context.account.id)
        account.permission_overrides = {"deny": ["support.read"]}
        await session.commit()
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=1)

    await notification_worker._process_delivery(SimpleNamespace(send_message=send_message), delivery.id)
    assert calls == []
    async with SessionFactory() as session:
        stored = await session.get(NotificationDelivery, delivery.id)
        assert stored.status == "suppressed"
    async with _client(context, context.user) as client:
        inbox = await client.get("/api/v1/notifications")
        assert inbox.status_code == 200
        assert str(notice.id) not in {row["id"] for row in inbox.json()["items"]}
        read = await client.post(f"/api/v1/notifications/{notice.id}/read")
        assert read.status_code == 404


async def test_full_support_reply_delivery_records_success_and_is_not_resent():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    async with _client(context, customer) as client:
        response = await client.post(
            f"/api/v1/admin/support/tickets/{ticket.id}/messages",
            headers=_write_headers(), json={"body": "Reply <literal> & text"},
        )
        assert response.status_code == 201
        outbox_id = uuid.UUID(response.json()["outbox_id"])
    async with SessionFactory() as session:
        row = await session.get(SupportOutbox, outbox_id)
        row.status = "sending"
        row.attempts = 1
        await session.commit()
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=77)

    bot = SimpleNamespace(send_message=send_message)
    await support_worker._process(bot, outbox_id)
    await support_worker._process(bot, outbox_id)
    assert len(calls) == 1
    assert calls[0]["chat_id"] == customer.telegram_id
    assert "Reply <literal> & text" in calls[0]["text"]
    async with _client(context, customer) as client:
        detail = (await client.get(f"/api/v1/admin/support/tickets/{ticket.id}")).json()
        message = detail["messages"][-1]
        assert message["delivery_status"] == "sent"
        assert message["delivery_attempts"] == 1
        assert message["sent_at"]


async def test_support_retry_is_visible_without_exposing_error_details():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    async with _client(context, customer) as client:
        response = await client.post(
            f"/api/v1/admin/control/tickets/{ticket.id}/reply",
            headers=_write_headers(), json={"body": "Retryable reply"},
        )
        assert response.status_code == 200, response.text
        outbox_id = uuid.UUID(response.json()["outbox_id"])
    async with SessionFactory() as session:
        row = await session.get(SupportOutbox, outbox_id)
        row.status = "sending"
        row.attempts = 1
        await session.commit()

    async def send_message(**kwargs):
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=customer.telegram_id, text="Synthetic"),
            message="Synthetic rate limit", retry_after=3,
        )

    await support_worker._process(SimpleNamespace(send_message=send_message), outbox_id)
    async with _client(context, customer) as client:
        response = await client.get(f"/api/v1/admin/support/tickets/{ticket.id}")
        message = response.json()["messages"][-1]
        assert message["delivery_status"] == "retry"
        assert message["delivery_attempts"] == 1
        assert "last_error" not in message


async def test_bot_contact_recovers_only_reachable_support_failures():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    _, other_customer = await _actors()
    other_ticket = await _ticket(other_customer)
    async with SessionFactory() as session:
        rows = []
        for owner_ticket, error in [
            (ticket, "telegram_forbidden:bot was blocked by the user"),
            (ticket, "telegram_api:cannot parse entities"),
            (other_ticket, "telegram_api:Bad Request: chat not found"),
        ]:
            message = SupportMessage(
                id=uuid.uuid4(), ticket_id=owner_ticket.id,
                user_id=context.user.id, is_admin=True, body="Deferred synthetic reply",
            )
            outbox = SupportOutbox(
                ticket_id=owner_ticket.id, message_id=message.id, admin_user_id=context.account.id,
                status="failed", attempts=8, last_error=error,
            )
            session.add(message)
            await session.flush()
            session.add(outbox)
            rows.append(outbox)
        await session.commit()
        recovered = await NotificationDeliveryService.requeue_reachable_user_deliveries(
            session, user_id=customer.id,
        )
        await session.commit()
        assert recovered == 1
        await session.refresh(rows[0])
        assert rows[0].status == "retry"
        assert rows[0].attempts == 0
        await session.refresh(rows[1])
        await session.refresh(rows[2])
        assert rows[1].status == rows[2].status == "failed"


async def test_cross_surface_concurrent_admin_reply_is_one_command():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    headers = _write_headers()
    async with _client(context, customer) as client:
        responses = await asyncio.gather(
            client.post(
                f"/api/v1/admin/support/tickets/{ticket.id}/messages",
                headers=headers, json={"body": "Concurrent answer"},
            ),
            client.post(
                f"/api/v1/admin/control/tickets/{ticket.id}/reply",
                headers=headers, json={"body": "Concurrent answer"},
            ),
        )
    assert all(response.status_code in {200, 201} for response in responses)
    assert len({response.json()["message_id"] for response in responses}) == 1
    assert sorted(response.json()["idempotency_replayed"] for response in responses) == [False, True]
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(SupportOutbox).where(
            SupportOutbox.ticket_id == ticket.id,
        )) == 1


async def test_support_read_and_write_permissions_are_enforced_by_both_http_surfaces():
    context, customer = await _actors()
    ticket = await _ticket(customer)
    context.account.permission_overrides = {"deny": ["support.read", "support.manage"]}
    async with _client(context, customer) as client:
        for path in [
            "/api/v1/admin/support/tickets",
            "/api/v1/admin/control/tickets",
            f"/api/v1/admin/support/tickets/{ticket.id}",
            f"/api/v1/admin/control/tickets/{ticket.id}",
        ]:
            response = await client.get(path)
            assert response.status_code == 403
        for path in [
            f"/api/v1/admin/support/tickets/{ticket.id}/messages",
            f"/api/v1/admin/control/tickets/{ticket.id}/reply",
        ]:
            response = await client.post(path, headers=_write_headers(), json={"body": "Denied"})
            assert response.status_code == 403
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id,
        )) == 0


async def test_configured_operator_notice_is_deduplicated_and_delivered_with_chat_link(monkeypatch):
    from app.db.profile_models import UserPreference
    from app.services.support import SupportConversationService

    context, customer = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(context.user.telegram_id))
    monkeypatch.setattr(settings, "public_base_url", "https://support.example")
    async with _client(context, customer) as client:
        response = await client.post("/api/v1/support/tickets", json={"topic": "Delivery", "message": "Private detail"})
        ticket_id = uuid.UUID(response.json()["id"])
    async with SessionFactory() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        message = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket_id))
        await SupportConversationService.notify_operators(session, ticket=ticket, message=message)
        session.add(UserPreference(user_id=context.user.id, notifications_enabled=False))
        notices = (await session.scalars(select(Notification).where(
            Notification.user_id == context.user.id, Notification.kind == "support_incoming",
        ))).all()
        assert len(notices) == 1
        notice = notices[0]
        deliveries = (await session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notice.id,
        ))).all()
        assert len(deliveries) == 1
        delivery = deliveries[0]
        delivery.status = "sending"
        delivery.attempts = 1
        await session.commit()
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=72)

    bot = SimpleNamespace(send_message=send_message)
    await notification_worker._process_delivery(bot, delivery.id)
    await notification_worker._process_delivery(bot, delivery.id)
    assert len(calls) == 1
    assert calls[0]["chat_id"] == context.user.telegram_id
    assert "Private detail" not in calls[0]["text"]
    assert calls[0]["reply_markup"].inline_keyboard[0][0].web_app.url == (
        f"https://support.example/admin-app/?support_ticket={ticket_id}"
    )


async def test_operator_revocation_serializes_with_inflight_support_notice(monkeypatch):
    context, customer = await _actors()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(context.user.telegram_id))
    async with _client(context, customer) as client:
        response = await client.post("/api/v1/support/tickets", json={"topic": "Race", "message": "Private"})
        assert response.status_code == 201
    async with SessionFactory() as session:
        notice = await session.scalar(select(Notification).where(
            Notification.user_id == context.user.id, Notification.kind == "support_incoming",
        ))
        delivery = await session.scalar(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notice.id,
        ))
        delivery.status = "sending"
        delivery.attempts = 1
        await session.commit()
    sending = asyncio.Event()
    release = asyncio.Event()
    revoking = asyncio.Event()

    async def send_message(**kwargs):
        sending.set()
        await release.wait()
        return SimpleNamespace(message_id=73)

    async def revoke():
        async with SessionFactory() as session:
            account = await session.get(AdminAccount, context.account.id)
            account.permission_overrides = {"deny": ["support.read"]}
            revoking.set()
            await session.commit()

    send_task = asyncio.create_task(notification_worker._process_delivery(
        SimpleNamespace(send_message=send_message), delivery.id,
    ))
    await asyncio.wait_for(sending.wait(), timeout=5)
    revoke_task = asyncio.create_task(revoke())
    try:
        await asyncio.wait_for(revoking.wait(), timeout=5)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(revoke_task), timeout=0.2)
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(send_task, revoke_task), timeout=5)


async def test_composed_support_routes_have_one_canonical_handler_and_paging_contract():
    from fastapi.routing import APIRoute
    from app.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    paths = (
        "/api/v1/admin/support/tickets",
        "/api/v1/admin/support/tickets/{ticket_id}",
    )
    def leaf_routes(routes):
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                yield from leaf_routes(nested.routes)
            elif isinstance(route, APIRoute):
                yield route

    for path in paths:
        handlers = [
            route for route in leaf_routes(app.routes)
            if route.path.endswith(path.removeprefix("/api/v1")) and "GET" in route.methods
        ]
        assert len(handlers) == 1, f"Duplicate or missing GET handler: {path}"
        assert handlers[0].endpoint.__module__ == "app.api.v1.admin_operations"
    schema = app.openapi()
    list_params = {item["name"] for item in schema["paths"][paths[0]]["get"]["parameters"]}
    detail_params = {item["name"] for item in schema["paths"][paths[1]]["get"]["parameters"]}
    assert {"q", "status", "limit", "offset"} <= list_params
    assert {"message_limit", "before"} <= detail_params


@pytest.mark.parametrize("delayed_admin", [False, True])
async def test_message_order_follows_ticket_lock_after_an_older_transaction_waits(delayed_admin):
    from app.services.admin_support import AdminSupportService
    from app.services.support import SupportConversationService

    context, customer = await _actors()
    ticket = await _ticket(customer)

    async def write_message(session, *, is_admin, body):
        if is_admin:
            result, _ = await AdminSupportService.reply_ticket(
                session, admin=context.account, ticket_id=ticket.id, body=body,
                idempotency_key=str(uuid.uuid4()), request_id="support-order-regression",
                confirmed=True,
            )
            return await session.get(SupportMessage, uuid.UUID(result["message_id"]))
        locked_ticket = await session.scalar(
            select(SupportTicket).where(SupportTicket.id == ticket.id).with_for_update()
        )
        return await SupportConversationService.add_customer_message(
            session, ticket=locked_ticket, user=customer, body=body,
        )

    async with SessionFactory() as delayed_session:
        # PostgreSQL now() stays at this older transaction start, even after a lock wait.
        await delayed_session.scalar(select(func.now()))
        async with SessionFactory() as first_session:
            first = await write_message(first_session, is_admin=not delayed_admin, body="First writer")
            delayed = asyncio.create_task(write_message(
                delayed_session, is_admin=delayed_admin, body="Writer after the lock",
            ))
            try:
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(delayed), timeout=0.1)
                await first_session.commit()
                latest = await asyncio.wait_for(delayed, timeout=5)
            finally:
                if not delayed.done():
                    delayed.cancel()
                    await asyncio.gather(delayed, return_exceptions=True)
        await delayed_session.commit()
        assert latest.created_at > first.created_at

    async with _client(context, customer) as client:
        detail = await client.get(f"/api/v1/admin/support/tickets/{ticket.id}")
        listing = await client.get("/api/v1/admin/support/tickets")
    assert detail.status_code == listing.status_code == 200
    assert [item["body"] for item in detail.json()["messages"]] == [
        "First writer", "Writer after the lock",
    ]
    item = next(item for item in listing.json()["items"] if item["id"] == str(ticket.id))
    assert item["last_message"]["id"] == str(latest.id)
    assert item["needs_reply"] is (not delayed_admin)
