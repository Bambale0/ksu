from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdminAccount, Notification, SupportMessage, SupportTicket, User
from app.services.abuse_protection import AbuseProtectionService
from app.services.support_recipient_config import SupportRecipientConfigService
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

SUPPORT_INCOMING_KIND = "support_incoming"


class SupportConversationService:
    """Persist customer activity and notify the explicitly configured operators."""

    @staticmethod
    async def consume_customer_message_quota(redis: Redis, *, user_id: uuid.UUID) -> None:
        await AbuseProtectionService.consume(
            redis,
            key=f"abuse:support:user:{user_id}",
            limit=settings.support_message_rate_limit_per_minute,
            window_seconds=60,
            message="Слишком много сообщений в поддержку. Попробуйте чуть позже.",
        )

    @staticmethod
    async def authorized_operator(
        session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False,
    ) -> bool:
        policy = await SupportRecipientConfigService.policy(session, lock=lock)
        recipient_ids = SupportRecipientConfigService.admin_ids(policy)
        if not recipient_ids:
            return False
        statement = (
            select(User, AdminAccount)
            .join(AdminAccount, AdminAccount.user_id == User.id)
            .where(
                User.id == user_id,
                AdminAccount.id.in_(recipient_ids),
                User.is_active.is_(True),
                AdminAccount.is_active.is_(True),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            # Membership lock precedes account locks everywhere that discloses a notice.
            statement = statement.with_for_update(read=True, of=(User, AdminAccount))
        row = (await session.execute(statement)).first()
        return bool(row and SupportRecipientConfigService.eligible(row[0], row[1]))

    @staticmethod
    async def add_customer_message(
        session: AsyncSession, *, ticket: SupportTicket, user: User, body: str,
    ) -> SupportMessage:
        if ticket.user_id != user.id:
            raise ValueError("Support message owner mismatch")
        text = body.strip()
        if not text:
            raise ValueError("Message is required")
        # The caller holds the ticket lock; DB now() would retain transaction-start time.
        now = datetime.now(UTC)
        message = SupportMessage(
            id=uuid.uuid4(), ticket_id=ticket.id, user_id=user.id, body=text, created_at=now,
        )
        ticket.updated_at = now
        session.add(message)
        await session.flush()
        await SupportConversationService.notify_operators(session, ticket=ticket, message=message)
        return message

    @staticmethod
    async def notify_operators(
        session: AsyncSession, *, ticket: SupportTicket, message: SupportMessage,
    ) -> None:
        await SupportRecipientConfigService.seed_from_bootstrap(session)
        policy = await SupportRecipientConfigService.policy(session, lock=True)
        recipient_ids = SupportRecipientConfigService.admin_ids(policy)
        recipients = []
        if recipient_ids:
            rows = (
                await session.execute(
                    select(User, AdminAccount)
                    .join(AdminAccount, AdminAccount.user_id == User.id)
                    .where(
                        AdminAccount.id.in_(recipient_ids),
                        User.is_active.is_(True),
                        AdminAccount.is_active.is_(True),
                    )
                    .with_for_update(read=True, of=(User, AdminAccount))
                    .execution_options(populate_existing=True)
                )
            ).all()
            recipients = [
                user for user, account in rows
                if SupportRecipientConfigService.eligible(user, account)
            ]
        for recipient in recipients:
            # Retrying this same persisted message cannot produce another notice.
            notification_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"ksu:support-incoming:{message.id}:{recipient.id}",
            )
            await session.execute(
                pg_insert(Notification)
                .values(
                    id=notification_id,
                    user_id=recipient.id,
                    kind=SUPPORT_INCOMING_KIND,
                    title="Новое сообщение в поддержку",
                    body=(
                        "В обращении есть новое сообщение. Откройте диалог в админке."
                        f"\n\nОбращение: {ticket.id}"
                    ),
                    is_read=False,
                )
                .on_conflict_do_nothing(index_elements=[Notification.id])
            )
            await NotificationService.enqueue_existing(
                session, notification_id=notification_id, purpose="transactional",
            )
        logger.log(
            logging.INFO if recipients else logging.WARNING,
            "support_incoming_queued" if recipients else "support_incoming_without_operator",
            extra={
                "ticket_id": str(ticket.id),
                "message_id": str(message.id),
                "user_id": str(ticket.user_id),
                "recipient_count": len(recipients),
            },
        )
