from __future__ import annotations

import asyncio
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.observability import (
    WORKER_LOOP_ERRORS,
    record_distributed_event,
    record_worker_heartbeat,
)
from app.db.session import engine
from app.services.generation_worker import GenerationWorkerService
from app.services.generations import GenerationService

logger = logging.getLogger(__name__)
WORKER_NAME = "generation-worker"


async def _event(redis: Redis, name: str) -> None:
    try:
        await record_distributed_event(redis, name)
    except Exception:
        logger.exception("Could not record distributed event %s", name)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    next_recovery_at = 0.0
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish generation worker heartbeat")

            now = time.monotonic()
            if now >= next_recovery_at:
                try:
                    await GenerationWorkerService.recovery_once()
                except Exception:
                    WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                    logger.exception("Generation recovery pass failed")
                    await _event(redis, "generation_reconcile_failure")
                next_recovery_at = now + settings.generation_reconcile_interval_seconds

            try:
                processed = await GenerationWorkerService.process_one(redis)
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Generation outbox worker iteration failed")
                await _event(redis, "generation_worker_loop_error")
                processed = False

            if processed:
                await _event(redis, "generation_submit_success")
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
