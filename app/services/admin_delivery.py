from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_models import NotificationCampaignDelivery, SupportOutbox
from app.db.models import SupportTicket

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def retry_delay(attempts: int) -> int:
    return min(900, max(5, 2 ** max(1, min(attempts, 9))))


class SupportOutboxDeliveryService:
    @staticmethod
    async def requeue_reachable_user_deliveries(
        session: AsyncSession, *, user_id: uuid.UUID,
    ) -> int:
        """Schedule this user's entire recoverable backlog after private contact."""
        await session.flush()
        # One SQL update avoids truncating the recovery signal or silently losing
        # a temporarily locked row. Actual sends still use bounded worker claims.
        result = await session.execute(
            update(SupportOutbox)
            .where(
                SupportOutbox.ticket_id.in_(
                    select(SupportTicket.id).where(SupportTicket.user_id == user_id)
                ),
                SupportOutbox.status.in_(["failed", "undeliverable"]),
                or_(
                    SupportOutbox.last_error.ilike("%chat not found%"),
                    SupportOutbox.last_error.ilike("%bot was blocked%"),
                ),
            )
            .values(
                status="retry", attempts=0, available_at=utcnow(),
                lease_until=None, last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

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
                                SupportOutbox.status.in_(["claimed", "sending"]),
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
        claimed = []
        for row in rows:
            if row.status == "sending":
                # A transport call may already have succeeded before its worker died.
                SupportOutboxDeliveryService.unknown(row, error="send_lease_expired")
                continue
            row.status = "claimed"
            row.lease_until = now + timedelta(seconds=settings.support_outbox_lease_seconds)
            row.last_error = None
            claimed.append(row)
        await session.flush()
        return claimed

    @staticmethod
    def start_sending(row: SupportOutbox) -> None:
        row.status = "sending"
        row.attempts += 1
        row.lease_until = utcnow() + timedelta(seconds=settings.support_outbox_lease_seconds)
        row.last_error = None

    @staticmethod
    def unknown(row: SupportOutbox, *, error: str) -> None:
        SupportOutboxDeliveryService.terminal(row, status="delivery_unknown", error=error)
        logger.warning(
            "support_reply_delivery_ambiguous",
            extra={
                "outbox_id": str(row.id), "ticket_id": str(row.ticket_id),
                "message_id": str(row.message_id), "attempts": row.attempts,
                "reason": error,
            },
        )

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
