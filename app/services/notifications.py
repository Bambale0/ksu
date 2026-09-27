from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Notification
from app.db.notification_models import NotificationDelivery


def utcnow() -> datetime:
    return datetime.now(UTC)


class NotificationService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        kind: str,
        title: str,
        body: str,
        purpose: str = "transactional",
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            is_read=False,
        )
        session.add(notification)
        await session.flush()
        await NotificationService.enqueue_existing(
            session,
            notification_id=notification.id,
            purpose=purpose,
        )
        return notification

    @staticmethod
    async def enqueue_existing(
        session: AsyncSession,
        *,
        notification_id: uuid.UUID,
        purpose: str = "transactional",
    ) -> None:
        stmt = (
            pg_insert(NotificationDelivery)
            .values(
                notification_id=notification_id,
                channel="telegram",
                purpose=purpose,
                status="pending",
                attempts=0,
                available_at=utcnow(),
            )
            .on_conflict_do_nothing(constraint="uq_notification_delivery_channel")
        )
        await session.execute(stmt)


class NotificationDeliveryService:
    @staticmethod
    async def claim_batch(session: AsyncSession) -> list[NotificationDelivery]:
        now = utcnow()
        rows = list(
            (
                await session.scalars(
                    select(NotificationDelivery)
                    .where(
                        or_(
                            and_(
                                NotificationDelivery.status.in_(["pending", "retry"]),
                                NotificationDelivery.available_at <= now,
                            ),
                            and_(
                                NotificationDelivery.status == "sending",
                                NotificationDelivery.lease_until.is_not(None),
                                NotificationDelivery.lease_until <= now,
                            ),
                        )
                    )
                    .order_by(NotificationDelivery.available_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(settings.notification_delivery_batch_size)
                )
            ).all()
        )
        lease_until = now + timedelta(seconds=settings.notification_delivery_lease_seconds)
        for row in rows:
            row.status = "sending"
            row.attempts += 1
            row.lease_until = lease_until
            row.last_error = None
        await session.flush()
        return rows

    @staticmethod
    async def requeue_reachable_user_deliveries(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        """Re-arm transactional Telegram deliveries after the user contacts the bot.

        A Mini App user can exist before Telegram allows the bot to initiate a
        private chat. Chat-not-found and bot-blocked errors are deferred delivery
        states, not permanent data loss. An incoming user message proves the chat
        is reachable again and safely starts a fresh retry cycle.
        """

        now = utcnow()
        rows = list(
            (
                await session.scalars(
                    select(NotificationDelivery)
                    .join(
                        Notification,
                        Notification.id == NotificationDelivery.notification_id,
                    )
                    .where(
                        Notification.user_id == user_id,
                        NotificationDelivery.channel == "telegram",
                        NotificationDelivery.purpose == "transactional",
                        NotificationDelivery.status.in_(["failed", "undeliverable"]),
                        or_(
                            NotificationDelivery.last_error.ilike("%chat not found%"),
                            NotificationDelivery.last_error.ilike("%bot was blocked%"),
                        ),
                    )
                    .order_by(NotificationDelivery.updated_at.asc())
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for row in rows:
            row.status = "retry"
            row.attempts = 0
            row.available_at = now
            row.lease_until = None
            row.last_error = None
        await session.flush()
        return len(rows)

    @staticmethod
    async def mark_sent(
        session: AsyncSession,
        delivery: NotificationDelivery,
        *,
        external_message_id: str | None,
    ) -> None:
        delivery.status = "sent"
        delivery.sent_at = utcnow()
        delivery.lease_until = None
        delivery.external_message_id = external_message_id
        delivery.last_error = None
        await session.flush()

    @staticmethod
    async def mark_terminal(
        session: AsyncSession,
        delivery: NotificationDelivery,
        *,
        status: str,
        error: str,
    ) -> None:
        delivery.status = status
        delivery.lease_until = None
        delivery.last_error = error[:4000]
        await session.flush()

    @staticmethod
    async def mark_retry(
        session: AsyncSession,
        delivery: NotificationDelivery,
        *,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        if delivery.attempts >= settings.notification_delivery_max_attempts:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="failed",
                error=error,
            )
            return
        if retry_after_seconds is None:
            exponent = max(0, delivery.attempts - 1)
            retry_after_seconds = min(
                settings.notification_retry_max_seconds,
                settings.notification_retry_base_seconds * (2**exponent),
            )
        delivery.status = "retry"
        delivery.lease_until = None
        delivery.available_at = utcnow() + timedelta(seconds=max(1, retry_after_seconds))
        delivery.last_error = error[:4000]
        await session.flush()
