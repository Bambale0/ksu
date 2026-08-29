from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import WORKER_LOOP_ERRORS, record_worker_heartbeat
from app.providers.kie import KieClient
from app.services.kie_credit_alerts import KieCreditAlertService

logger = logging.getLogger(__name__)
WORKER_NAME = "kie-credit-alert-worker"


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(settings.bot_token) if settings.bot_token else None
    client = KieClient(settings.kie_api_key, settings.kie_base_url) if settings.kie_api_key else None
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish Kie credit alert worker heartbeat")

            if bot is not None and client is not None:
                try:
                    await KieCreditAlertService.check_once(redis=redis, bot=bot, client=client)
                except Exception:
                    WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                    logger.exception("Kie credit alert worker iteration failed")

            await asyncio.sleep(max(60, int(settings.kie_credit_alert_poll_seconds)))
    finally:
        if client is not None:
            await client.aclose()
        if bot is not None:
            await bot.session.close()
        await redis.aclose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
