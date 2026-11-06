from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.admin_models import SupportOutbox
from app.db.models import AdminAccount, SupportMessage, SupportTicket, User
from app.db.session import SessionFactory
from app.services.admin_delivery import SupportOutboxDeliveryService
from app.services.notifications import NotificationDeliveryService
from app.workers import admin_support as support_worker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def recovery_rows(monkeypatch):
    monkeypatch.setattr(settings, "support_outbox_batch_size", 3)
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        users = [
            User(
                telegram_id=9_500_000_000_000 + uuid.uuid4().int % 100_000_000_000,
                first_name="Synthetic support recovery",
            )
            for _ in range(3)
        ]
        session.add_all(users)
        await session.flush()
        admin = AdminAccount(
            user_id=users[0].id, role="support", permission_overrides={}, is_active=True,
        )
        session.add(admin)
        await session.flush()
        tickets = [
            SupportTicket(user_id=users[1].id, topic="Synthetic backlog"),
            SupportTicket(user_id=users[2].id, topic="Unrelated backlog"),
        ]
        session.add_all(tickets)
        await session.flush()
        oldest = await session.scalar(select(func.min(SupportOutbox.created_at)))
        backlog_time = min(now, oldest or now) - timedelta(days=1)
        rows, recoverable, preserved = [], [], []
        cases = [
            (tickets[0], "undeliverable", "telegram_api:Bad Request: chat not found")
            for _ in range(8)
        ] + [
            (tickets[0], "failed", "telegram_forbidden:bot was blocked by the user"),
            (tickets[0], "sent", "telegram_api:Bad Request: chat not found"),
            (tickets[0], "sending", "telegram_forbidden:bot was blocked by the user"),
            (tickets[0], "failed", "telegram_api:cannot parse entities"),
            (tickets[1], "undeliverable", "telegram_api:Bad Request: chat not found"),
        ]
        for index, (ticket, status, error) in enumerate(cases):
            message = SupportMessage(
                id=uuid.uuid4(), ticket_id=ticket.id, user_id=users[0].id,
                is_admin=True, body=f"Synthetic deferred reply {index}",
            )
            session.add(message)
            await session.flush()
            row = SupportOutbox(
                id=uuid.uuid4(), ticket_id=ticket.id, message_id=message.id,
                admin_user_id=admin.id, status=status, attempts=8,
                created_at=backlog_time + timedelta(milliseconds=index),
                available_at=now, last_error=error,
                lease_until=now + timedelta(minutes=5) if status == "sending" else None,
            )
            session.add(row)
            rows.append(row)
            if index < 9:
                recoverable.append(row.id)
            else:
                preserved.append((row.id, status, row.attempts, error))
        await session.commit()
    try:
        yield SimpleNamespace(
            customer=users[1], rows=rows, recoverable=recoverable, preserved=preserved,
        )
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(SupportOutbox).where(SupportOutbox.id.in_([row.id for row in rows])))
            await session.execute(delete(SupportMessage).where(SupportMessage.ticket_id.in_([t.id for t in tickets])))
            await session.execute(delete(SupportTicket).where(SupportTicket.id.in_([t.id for t in tickets])))
            await session.execute(delete(AdminAccount).where(AdminAccount.id == admin.id))
            await session.execute(delete(User).where(User.id.in_([user.id for user in users])))
            await session.commit()


async def test_one_contact_recovers_entire_backlog_and_worker_drains_bounded_batches(recovery_rows):
    data = recovery_rows
    async with SessionFactory() as session:
        recovered = await NotificationDeliveryService.requeue_reachable_user_deliveries(
            session, user_id=data.customer.id,
        )
        await session.commit()
    assert recovered == len(data.recoverable), "Contact must not strand replies beyond the worker batch size"

    async with SessionFactory() as session:
        recovered_again = await NotificationDeliveryService.requeue_reachable_user_deliveries(
            session, user_id=data.customer.id,
        )
        await session.commit()
    assert recovered_again == 0
    async with SessionFactory() as session:
        for row_id in data.recoverable:
            row = await session.get(SupportOutbox, row_id)
            assert row.status == "retry" and row.attempts == 0
            assert row.last_error is None and row.lease_until is None
        for row_id, status, attempts, error in data.preserved:
            row = await session.get(SupportOutbox, row_id)
            assert (row.status, row.attempts, row.last_error) == (status, attempts, error)

    delivered = []

    class SyntheticBot:
        async def send_message(self, **kwargs):
            delivered.append(kwargs)
            return SimpleNamespace(message_id=len(delivered))

    bot = SyntheticBot()
    claimed_ids = []
    while len(claimed_ids) < len(data.recoverable):
        async with SessionFactory() as session:
            batch = await SupportOutboxDeliveryService.claim_batch(session)
            ids = [row.id for row in batch]
            await session.commit()
        assert len(ids) <= settings.support_outbox_batch_size
        assert ids
        assert set(ids) <= set(data.recoverable)
        claimed_ids.extend(ids)
        for row_id in ids:
            await support_worker._process(bot, row_id)
    assert set(claimed_ids) == set(data.recoverable)
    assert len(claimed_ids) == len(data.recoverable) == len(delivered)
    assert all(item["chat_id"] == data.customer.telegram_id for item in delivered)
    async with SessionFactory() as session:
        for row_id in data.recoverable:
            row = await session.get(SupportOutbox, row_id)
            assert row.status == "sent" and row.attempts == 1


async def test_contact_does_not_silently_skip_a_temporarily_locked_recoverable_reply(recovery_rows):
    data = recovery_rows

    async def recover():
        async with SessionFactory() as session:
            count = await SupportOutboxDeliveryService.requeue_reachable_user_deliveries(
                session, user_id=data.customer.id,
            )
            await session.commit()
            return count

    async with SessionFactory() as locker:
        await locker.scalar(
            select(SupportOutbox).where(SupportOutbox.id == data.recoverable[0]).with_for_update()
        )
        pending = asyncio.create_task(recover())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(pending), timeout=0.1)
            await locker.commit()
            assert await asyncio.wait_for(pending, timeout=5) == len(data.recoverable)
        finally:
            await locker.rollback()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
