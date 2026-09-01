from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import record_worker_heartbeat
from app.db.admin_models import SupportOutbox
from app.db.models import SupportMessage, SupportTicket, User
from app.db.session import SessionFactory
from app.services.admin_delivery import SupportOutboxDeliveryService

logger = logging.getLogger(__name__)
WORKER_NAME = "admin-support-worker"


async def _heartbeat(redis: Redis) -> None:
    try:
        await record_worker_heartbeat(redis, WORKER_NAME)
    except RedisError:
        logger.warning("Could not publish admin support worker heartbeat")


async def _process(bot: Bot, outbox_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        row = await session.get(SupportOutbox, outbox_id, with_for_update=True)
        if row is None or row.status != "sending":
            return
        ticket = await session.get(SupportTicket, row.ticket_id)
        message = await session.get(SupportMessage, row.message_id)
        if ticket is None or message is None:
            SupportOutboxDeliveryService.terminal(
                row,
                status="failed",
                error="support_ticket_or_message_missing",
            )
            await session.commit()
            return
        user = await session.get(User, ticket.user_id)
        if user is None or not user.is_active:
            SupportOutboxDeliveryService.terminal(
                row,
                status="undeliverable",
                error="user_inactive_or_missing",
            )
            await session.commit()
            return
        try:
            sent = await bot.send_message(
                chat_id=user.telegram_id,
                text=f"Ответ поддержки\n\n{message.body}",
            )
        except TelegramForbiddenError as exc:
            SupportOutboxDeliveryService.terminal(
                row,
                status="undeliverable",
                error=f"telegram_forbidden:{exc}",
            )
        except TelegramRetryAfter as exc:
            SupportOutboxDeliveryService.retry(
                row,
                error=f"telegram_retry_after:{exc}",
                retry_after=int(exc.retry_after),
            )
        except TelegramAPIError as exc:
            SupportOutboxDeliveryService.retry(row, error=f"telegram_api:{exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("admin_support_delivery_error", extra={"outbox_id": str(row.id)})
            SupportOutboxDeliveryService.retry(
                row,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )
        else:
            SupportOutboxDeliveryService.sent(row, external_message_id=str(sent.message_id))
        await session.commit()


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for the support outbox worker")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(settings.bot_token)
    try:
        while True:
            await _heartbeat(redis)
            async with SessionFactory() as session:
                claimed = await SupportOutboxDeliveryService.claim_batch(session)
                ids = [row.id for row in claimed]
                await session.commit()
            if not ids:
                await asyncio.sleep(settings.support_outbox_worker_poll_seconds)
                continue
            for outbox_id in ids:
                await _process(bot, outbox_id)
                await _heartbeat(redis)
    finally:
        await redis.aclose()
        await bot.session.close()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
