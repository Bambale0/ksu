from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import WORKER_LOOP_ERRORS, record_worker_heartbeat
from app.db.session import SessionFactory, engine
from app.providers.kie_credits import KieCreditClient
from app.services.kie_credit_alerts import KieCreditAlertService

logger = logging.getLogger(__name__)
WORKER_NAME = "kie-credit-alert-worker"


async def _heartbeat(redis: Redis) -> None:
    try:
        await record_worker_heartbeat(redis, WORKER_NAME)
    except RedisError:
        logger.warning("Could not publish Kie credit alert worker heartbeat")


async def run_once(*, redis: Redis, bot: Bot, client: KieCreditClient) -> None:
    async with SessionFactory() as session:
        await KieCreditAlertService.check_once(
            session=session,
            redis=redis,
            bot=bot,
            client=client,
        )


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(settings.bot_token) if settings.bot_token else None
    client = (
        KieCreditClient(settings.kie_api_key, settings.kie_base_url)
        if settings.kie_api_key
        else None
    )
    check_interval = max(60, int(settings.kie_credit_alert_poll_seconds))
    heartbeat_interval = max(10, min(60, int(settings.worker_stale_after_seconds) // 2))
    next_check = 0.0
    warned_unconfigured = False

    try:
        while True:
            await _heartbeat(redis)
            now = time.monotonic()
            if settings.kie_credit_alert_enabled and now >= next_check:
                next_check = now + check_interval
                if bot is None or client is None:
                    if not warned_unconfigured:
                        logger.warning(
                            "Kie credit monitoring is enabled but BOT_TOKEN or KIE_API_KEY is missing"
                        )
                        warned_unconfigured = True
                else:
                    try:
                        await run_once(redis=redis, bot=bot, client=client)
                    except Exception:
                        WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                        logger.exception("Kie credit alert worker iteration failed")
                    await _heartbeat(redis)
            await asyncio.sleep(heartbeat_interval)
    finally:
        if client is not None:
            await client.aclose()
        if bot is not None:
            await bot.session.close()
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
