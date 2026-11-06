from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.methods import SendMessage
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.admin_models import SupportOutbox
from app.db.models import AdminAccount, SupportMessage, SupportTicket, User
from app.db.session import SessionFactory
from app.services.admin_delivery import SupportOutboxDeliveryService
from app.services.admin_support import AdminSupportService
from app.workers import admin_support as worker

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def queued_reply(monkeypatch):
    monkeypatch.setattr(settings, "support_outbox_batch_size", 1)
    monkeypatch.setattr(settings, "support_outbox_lease_seconds", 2)
    monkeypatch.setattr(settings, "support_outbox_max_attempts", 3)
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        oldest = await session.scalar(select(func.min(SupportOutbox.created_at)))
        operator = User(
            telegram_id=8_800_000_000_000 + uuid.uuid4().int % 100_000_000_000,
            first_name="Synthetic ambiguity operator",
        )
        customer = User(
            telegram_id=8_900_000_000_000 + uuid.uuid4().int % 100_000_000_000,
            first_name="Synthetic ambiguity customer",
        )
        session.add_all([operator, customer])
        await session.flush()
        account = AdminAccount(user_id=operator.id, role="support", is_active=True)
        ticket = SupportTicket(user_id=customer.id, topic="Synthetic delivery ambiguity")
        session.add_all([account, ticket])
        await session.flush()
        message = SupportMessage(
            id=uuid.uuid4(), ticket_id=ticket.id, user_id=operator.id,
            is_admin=True, body="Synthetic reply remains available in the conversation",
        )
        outbox = SupportOutbox(
            ticket_id=ticket.id, message_id=message.id, message=message,
            admin_user_id=account.id, status="pending",
            available_at=now - timedelta(seconds=1),
            created_at=min(now, oldest or now) - timedelta(minutes=1),
        )
        session.add_all([message, outbox])
        await session.commit()
        fixture = SimpleNamespace(
            id=outbox.id, ticket_id=ticket.id, message_id=message.id,
            admin=account, customer=customer, operator=operator,
        )
    try:
        yield fixture
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(SupportOutbox).where(SupportOutbox.id == fixture.id))
            await session.execute(delete(SupportMessage).where(SupportMessage.id == fixture.message_id))
            await session.execute(delete(SupportTicket).where(SupportTicket.id == fixture.ticket_id))
            await session.execute(delete(AdminAccount).where(AdminAccount.id == fixture.admin.id))
            await session.execute(delete(User).where(User.id.in_([
                fixture.customer.id, fixture.operator.id,
            ])))
            await session.commit()


async def claim(fixture):
    async with SessionFactory() as session:
        rows = await SupportOutboxDeliveryService.claim_batch(session)
        ids = [row.id for row in rows]
        await session.commit()
    return ids


async def state(fixture):
    async with SessionFactory() as session:
        row = await session.get(SupportOutbox, fixture.id)
        return SimpleNamespace(
            status=row.status, attempts=row.attempts, lease_until=row.lease_until,
            last_error=row.last_error, sent_at=row.sent_at,
            external_message_id=row.external_message_id,
        )


async def make_due(fixture, *, expire_lease=False):
    async with SessionFactory() as session:
        row = await session.get(SupportOutbox, fixture.id)
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        if expire_lease:
            row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def assert_unknown_is_terminal_and_visible(fixture):
    actual = await state(fixture)
    assert actual.status == "delivery_unknown"
    assert actual.attempts == 1
    assert actual.lease_until is None
    assert actual.sent_at is None and actual.external_message_id is None
    async with SessionFactory() as session:
        assert await SupportOutboxDeliveryService.requeue_reachable_user_deliveries(
            session, user_id=fixture.customer.id,
        ) == 0
        rows = await SupportOutboxDeliveryService.claim_batch(session)
        assert fixture.id not in {row.id for row in rows}
        # Other suites may own pending rows; do not persist claims on those records.
        await session.rollback()
        view = await AdminSupportService.get_ticket(
            session, admin=fixture.admin, ticket_id=fixture.ticket_id,
        )
        item = next(row for row in view["messages"] if row["id"] == str(fixture.message_id))
        assert item["delivery_status"] == "delivery_unknown"
        assert item["body"] == "Synthetic reply remains available in the conversation"
        assert "last_error" not in item


@pytest.mark.parametrize("outcome", ["timeout", "network", "server", "unexpected"])
async def test_accepted_reply_with_unknown_transport_outcome_is_not_automatically_resent(
    queued_reply, outcome,
):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    accepted = []

    async def send_message(**kwargs):
        accepted.append(kwargs)
        method = SendMessage(chat_id=fixture.customer.telegram_id, text="Synthetic")
        if outcome == "timeout":
            raise TimeoutError("Synthetic lost response after acceptance")
        if outcome == "network":
            raise TelegramNetworkError(method=method, message="Synthetic response connection lost")
        if outcome == "server":
            raise TelegramServerError(method=method, message="Synthetic ambiguous upstream failure")
        raise RuntimeError("Synthetic response decode failure after acceptance")

    bot = SimpleNamespace(send_message=send_message)
    await worker._process(bot, fixture.id)
    await assert_unknown_is_terminal_and_visible(fixture)
    await worker._process(bot, fixture.id)
    assert len(accepted) == 1


async def test_real_worker_deadline_after_acceptance_is_not_retryable(queued_reply):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    accepted = []

    async def send_message(**kwargs):
        accepted.append(kwargs)
        await asyncio.Future()

    await asyncio.wait_for(
        worker._process(SimpleNamespace(send_message=send_message), fixture.id), timeout=3,
    )
    assert len(accepted) == 1
    await assert_unknown_is_terminal_and_visible(fixture)


async def test_crash_after_transport_started_does_not_replay_expired_sending_lease(queued_reply):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    accepted = []
    started = asyncio.Event()

    async def interrupted_send(**kwargs):
        accepted.append(kwargs)
        started.set()
        await asyncio.Future()

    task = asyncio.create_task(worker._process(
        SimpleNamespace(send_message=interrupted_send), fixture.id,
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert (await state(fixture)).status == "sending"
    await make_due(fixture, expire_lease=True)
    recovered = await claim(fixture)

    async def repeated_send(**kwargs):
        accepted.append(kwargs)
        return SimpleNamespace(message_id=84)

    for outbox_id in recovered:
        assert outbox_id == fixture.id
        await worker._process(SimpleNamespace(send_message=repeated_send), outbox_id)
    assert len(accepted) == 1, "A send accepted before a crash was replayed"
    await assert_unknown_is_terminal_and_visible(fixture)


async def test_unstarted_expired_claim_is_recovered_without_counting_a_send(queued_reply):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    first = await state(fixture)
    assert first.status == "claimed" and first.attempts == 0
    await make_due(fixture, expire_lease=True)
    assert await claim(fixture) == [fixture.id]
    assert (await state(fixture)).attempts == 0
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=85)

    await worker._process(SimpleNamespace(send_message=send_message), fixture.id)
    final = await state(fixture)
    assert final.status == "sent" and final.attempts == 1
    assert final.external_message_id == "85"
    assert len(calls) == 1


async def test_parallel_workers_start_the_transport_only_once(queued_reply):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def send_message(**kwargs):
        calls.append(kwargs)
        durable = await state(fixture)
        assert durable.status == "sending" and durable.attempts == 1
        entered.set()
        await release.wait()
        return SimpleNamespace(message_id=86)

    bot = SimpleNamespace(send_message=send_message)
    first = asyncio.create_task(worker._process(bot, fixture.id))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        second = asyncio.create_task(worker._process(bot, fixture.id))
        await asyncio.sleep(0.05)
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []))
    assert len(calls) == 1
    assert (await state(fixture)).status == "sent"


async def test_definitive_rate_limit_rejection_still_retries_then_sends(queued_reply):
    fixture = queued_reply
    assert await claim(fixture) == [fixture.id]
    attempts = []

    async def send_message(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=fixture.customer.telegram_id, text="Synthetic"),
                message="Synthetic explicit rate limit", retry_after=1,
            )
        return SimpleNamespace(message_id=87)

    bot = SimpleNamespace(send_message=send_message)
    await worker._process(bot, fixture.id)
    first = await state(fixture)
    assert first.status == "retry" and first.attempts == 1
    await make_due(fixture)
    assert await claim(fixture) == [fixture.id]
    await worker._process(bot, fixture.id)
    final = await state(fixture)
    assert final.status == "sent" and final.attempts == 2
    assert final.external_message_id == "87" and len(attempts) == 2


async def test_late_success_receipt_resolves_unknown_without_a_stale_error(
    queued_reply, monkeypatch,
):
    fixture = queued_reply
    monkeypatch.setattr(settings, "support_outbox_lease_seconds", 10)
    assert await claim(fixture) == [fixture.id]
    entered, release = asyncio.Event(), asyncio.Event()
    accepted = []

    async def send_message(**kwargs):
        accepted.append(kwargs)
        entered.set()
        await release.wait()
        return SimpleNamespace(message_id=88)

    task = asyncio.create_task(worker._process(
        SimpleNamespace(send_message=send_message), fixture.id,
    ))
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        await make_due(fixture, expire_lease=True)
        assert await claim(fixture) == []
        assert (await state(fixture)).status == "delivery_unknown"
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=3)
    actual = await state(fixture)
    assert actual.status == "sent" and actual.external_message_id == "88"
    assert actual.sent_at is not None and actual.lease_until is None
    assert actual.last_error is None
    assert actual.attempts == 1 and len(accepted) == 1
