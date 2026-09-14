from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import WORKER_LOOP_ERRORS, record_worker_heartbeat
from app.db.session import SessionFactory, engine
from app.services.nexus_admin_tasks import NexusAdminTaskService

logger = logging.getLogger(__name__)
WORKER_NAME = "nexus-test-worker"


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for nexus-test-worker")
    if not settings.nexus_api_key:
        raise RuntimeError("NEXUS_API_KEY is required for nexus-test-worker")

    bot = Bot(settings.bot_token)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish Nexus test worker heartbeat")

            try:
                async with SessionFactory() as session:
                    task_id = await NexusAdminTaskService.claim(session)
                if task_id is not None:
                    await NexusAdminTaskService.process(task_id, bot)
                    continue
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Nexus test worker iteration failed")
            await asyncio.sleep(settings.nexus_test_worker_poll_seconds)
    finally:
        await redis.aclose()
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
