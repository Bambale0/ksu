from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)


def _notification_text(notification: Notification) -> str:
    title = notification.title.strip()
    body = notification.body.strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body or "У вас новое уведомление."


async def _process_delivery(bot: Bot, delivery_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id, with_for_update=True)
        if delivery is None or delivery.status != "sending":
            return
        notification = await session.get(Notification, delivery.notification_id)
        if notification is None:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="failed",
                error="notification_missing",
            )
            await session.commit()
            return
        user = await session.get(User, notification.user_id)
        if user is None or not user.is_active:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="undeliverable",
                error="user_inactive_or_missing",
            )
            await session.commit()
            return
        preference = await session.get(UserPreference, user.id)
        if preference is not None and not preference.notifications_enabled:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="suppressed",
                error="notifications_disabled",
            )
            await session.commit()
            return
        if (
            delivery.purpose == "marketing"
            and preference is not None
            and not preference.marketing_notifications
        ):
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="suppressed",
                error="marketing_notifications_disabled",
            )
            await session.commit()
            return

        try:
            message = await bot.send_message(
                chat_id=user.telegram_id,
                text=_notification_text(notification),
            )
        except TelegramForbiddenError as exc:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="undeliverable",
                error=f"telegram_forbidden:{exc}",
            )
        except TelegramRetryAfter as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_retry_after:{exc}",
                retry_after_seconds=int(exc.retry_after),
            )
        except TelegramAPIError as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_api:{exc}",
            )
        except Exception as exc:  # noqa: BLE001 - worker must persist retry state before continuing
            logger.exception("notification_delivery_unexpected_error", extra={"delivery_id": str(delivery.id)})
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )
        else:
            await NotificationDeliveryService.mark_sent(
                session,
                delivery,
                external_message_id=str(message.message_id),
            )
        await session.commit()


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for the notification worker")
    bot = Bot(settings.bot_token)
    try:
        while True:
            async with SessionFactory() as session:
                claimed = await NotificationDeliveryService.claim_batch(session)
                delivery_ids = [row.id for row in claimed]
                await session.commit()
            if not delivery_ids:
                await asyncio.sleep(settings.notification_worker_poll_seconds)
                continue
            for delivery_id in delivery_ids:
                await _process_delivery(bot, delivery_id)
    finally:
        await bot.session.close()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
