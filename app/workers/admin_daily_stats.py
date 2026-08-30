from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import (
    WORKER_LOOP_ERRORS,
    record_distributed_event,
    record_worker_heartbeat,
)
from app.db.session import SessionFactory, engine
from app.services.admin_daily_stats import AdminDailyStatsService

logger = logging.getLogger(__name__)
WORKER_NAME = "admin-daily-stats-worker"


async def _event(redis: Redis, name: str) -> None:
    try:
        await record_distributed_event(redis, name)
    except Exception:
        logger.exception("Could not record distributed event %s", name)


async def _send_report(bot: Bot) -> int:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        if not await AdminDailyStatsService.due_to_send(
            session,
            now=now,
            interval_seconds=settings.admin_daily_stats_interval_seconds,
        ):
            return 0
        chat_ids = await AdminDailyStatsService.active_admin_chat_ids(session)
        marker_admin = await AdminDailyStatsService.active_admin_for_marker(session)
        if not chat_ids or marker_admin is None:
            logger.warning("Daily admin stats report skipped: no active admin chat")
            return 0
        report = AdminDailyStatsService.format_report(
            await AdminDailyStatsService.collect(session, now=now)
        )

    sent_count = 0
    sent_chat_ids: list[int] = []
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=report)
        except TelegramForbiddenError as exc:
            logger.warning("Daily admin stats recipient is unavailable: %s", exc)
        except TelegramRetryAfter as exc:
            logger.warning("Daily admin stats hit Telegram retry_after=%s", exc.retry_after)
        except TelegramAPIError as exc:
            logger.warning("Daily admin stats Telegram API error: %s", exc)
        else:
            sent_count += 1
            sent_chat_ids.append(chat_id)

    if sent_chat_ids:
        async with SessionFactory() as session:
            marker_admin = await AdminDailyStatsService.active_admin_for_marker(session)
            if marker_admin is not None:
                await AdminDailyStatsService.mark_sent(
                    session,
                    admin=marker_admin,
                    sent_at=now,
                    chat_ids=sent_chat_ids,
                )
                await session.commit()
    return sent_count


async def run() -> None:
    if not settings.admin_daily_stats_enabled:
        logger.info("Daily admin stats worker is disabled")
        return
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for the daily admin stats worker")

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(settings.bot_token)
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish daily admin stats worker heartbeat")

            try:
                sent_count = await _send_report(bot)
                if sent_count:
                    logger.info("Sent daily admin stats report to %s admins", sent_count)
                    await _event(redis, "admin_daily_stats_sent")
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Daily admin stats pass failed")
                await _event(redis, "admin_daily_stats_failure")
                await _event(redis, "admin_daily_stats_worker_loop_error")
            await asyncio.sleep(max(60, settings.admin_daily_stats_poll_seconds))
    finally:
        await bot.session.close()
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
