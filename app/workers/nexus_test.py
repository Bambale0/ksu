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
from app.services.seedance_admin_tasks import SeedanceAdminTaskService

logger = logging.getLogger(__name__)
WORKER_NAME = "nexus-test-worker"


async def _heartbeat(redis: Redis) -> None:
    try:
        await record_worker_heartbeat(redis, WORKER_NAME)
    except RedisError:
        logger.warning("Could not publish Nexus test worker heartbeat")


async def run() -> None:
    bot = Bot(settings.bot_token) if settings.bot_token else None
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    warned_unconfigured = False
    try:
        while True:
            await _heartbeat(redis)

            nexus_enabled = bool(settings.nexus_api_key.strip())
            seedance_enabled = bool(settings.neironych_api_key.strip())
            if bot is None or not (nexus_enabled or seedance_enabled):
                if not warned_unconfigured:
                    logger.warning(
                        "Admin test worker idle: BOT_TOKEN or provider API keys are not configured"
                    )
                    warned_unconfigured = True
                await asyncio.sleep(settings.nexus_test_worker_poll_seconds)
                continue

            warned_unconfigured = False
            try:
                if seedance_enabled:
                    async with SessionFactory() as session:
                        task_id = await SeedanceAdminTaskService.claim(session)
                    if task_id is not None:
                        await SeedanceAdminTaskService.process(task_id, bot)
                        await _heartbeat(redis)
                        continue

                if nexus_enabled:
                    async with SessionFactory() as session:
                        task_id = await NexusAdminTaskService.claim(session)
                    if task_id is not None:
                        await NexusAdminTaskService.process(task_id, bot)
                        await _heartbeat(redis)
                        continue
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Nexus test worker iteration failed")
            await asyncio.sleep(settings.nexus_test_worker_poll_seconds)
    finally:
        await redis.aclose()
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
