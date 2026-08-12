from __future__ import annotations

import asyncio
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.db.session import engine
from app.services.generation_worker import GenerationWorkerService
from app.services.generations import GenerationService

logger = logging.getLogger(__name__)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    next_recovery_at = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_recovery_at:
                try:
                    await GenerationWorkerService.recovery_once()
                except Exception:
                    logger.exception("Generation recovery pass failed")
                next_recovery_at = now + settings.generation_reconcile_interval_seconds

            try:
                processed = await GenerationWorkerService.process_one(redis)
            except Exception:
                logger.exception("Generation outbox worker iteration failed")
                processed = False

            if processed:
                continue

            try:
                await redis.blpop(
                    GenerationService.WAKE_KEY,
                    timeout=settings.generation_worker_poll_seconds,
                )
            except RedisError:
                logger.warning("Redis wake-up channel unavailable; polling durable outbox")
                await asyncio.sleep(settings.generation_worker_poll_seconds)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
