from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_models import NotificationCampaignDelivery, SupportOutbox


def utcnow() -> datetime:
    return datetime.now(UTC)


def retry_delay(attempts: int) -> int:
    return min(900, max(5, 2 ** max(1, min(attempts, 9))))


class SupportOutboxDeliveryService:
    @staticmethod
    async def claim_batch(session: AsyncSession) -> list[SupportOutbox]:
        now = utcnow()
        rows = list(
            (
                await session.scalars(
                    select(SupportOutbox)
                    .where(
                        SupportOutbox.available_at <= now,
                        or_(
                            SupportOutbox.status.in_(["pending", "retry"]),
                            and_(
                                SupportOutbox.status == "sending",
                                SupportOutbox.lease_until.is_not(None),
                                SupportOutbox.lease_until < now,
                            ),
                        ),
                    )
                    .order_by(SupportOutbox.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(settings.support_outbox_batch_size)
                )
            ).all()
        )
        for row in rows:
            row.status = "sending"
            row.attempts += 1
            row.lease_until = now + timedelta(seconds=settings.support_outbox_lease_seconds)
            row.last_error = None
        await session.flush()
        return rows

    @staticmethod
    def sent(row: SupportOutbox, *, external_message_id: str) -> None:
        row.status = "sent"
        row.sent_at = utcnow()
        row.external_message_id = external_message_id
        row.lease_until = None
        row.last_error = None

    @staticmethod
    def retry(row: SupportOutbox, *, error: str, retry_after: int | None = None) -> None:
        if row.attempts >= settings.support_outbox_max_attempts:
            row.status = "failed"
            row.lease_until = None
            row.last_error = error[:4000]
            return
        row.status = "retry"
        row.available_at = utcnow() + timedelta(
            seconds=max(1, retry_after if retry_after is not None else retry_delay(row.attempts))
        )
        row.lease_until = None
        row.last_error = error[:4000]

    @staticmethod
    def terminal(row: SupportOutbox, *, status: str, error: str) -> None:
        row.status = status
        row.lease_until = None
        row.last_error = error[:4000]


class CampaignDeliveryService:
    @staticmethod
    async def claim_batch(session: AsyncSession) -> list[NotificationCampaignDelivery]:
        now = utcnow()
        rows = list(
            (
                await session.scalars(
                    select(NotificationCampaignDelivery)
                    .where(
                        NotificationCampaignDelivery.available_at <= now,
                        or_(
                            NotificationCampaignDelivery.status.in_(["pending", "retry"]),
                            and_(
                                NotificationCampaignDelivery.status == "sending",
                                NotificationCampaignDelivery.lease_until.is_not(None),
                                NotificationCampaignDelivery.lease_until < now,
                            ),
                        ),
                    )
                    .order_by(NotificationCampaignDelivery.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(settings.campaign_delivery_batch_size)
                )
            ).all()
        )
        for row in rows:
            row.status = "sending"
            row.attempts += 1
            row.lease_until = now + timedelta(seconds=settings.campaign_delivery_lease_seconds)
            row.last_error = None
        await session.flush()
        return rows

    @staticmethod
    def sent(row: NotificationCampaignDelivery, *, external_message_id: str) -> None:
        row.status = "sent"
        row.sent_at = utcnow()
        row.external_message_id = external_message_id
        row.lease_until = None
        row.last_error = None

    @staticmethod
    def retry(
        row: NotificationCampaignDelivery,
        *,
        error: str,
        retry_after: int | None = None,
    ) -> None:
        if row.attempts >= settings.campaign_delivery_max_attempts:
            row.status = "failed"
            row.lease_until = None
            row.last_error = error[:4000]
            return
        row.status = "retry"
        row.available_at = utcnow() + timedelta(
            seconds=max(1, retry_after if retry_after is not None else retry_delay(row.attempts))
        )
        row.lease_until = None
        row.last_error = error[:4000]

    @staticmethod
    def terminal(row: NotificationCampaignDelivery, *, status: str, error: str) -> None:
        row.status = status
        row.lease_until = None
        row.last_error = error[:4000]
