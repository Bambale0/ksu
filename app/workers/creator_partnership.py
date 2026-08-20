from __future__ import annotations

import asyncio
import logging

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
from app.services.creator_partnership import CreatorPartnershipService

logger = logging.getLogger(__name__)
WORKER_NAME = "creator-partnership-worker"


async def _event(redis: Redis, name: str) -> None:
    try:
        await record_distributed_event(redis, name)
    except Exception:
        logger.exception("Could not record distributed event %s", name)


async def run_once() -> int:
    async with SessionFactory() as session:
        try:
            created = await CreatorPartnershipService.grant_due_current_period(session)
            await session.commit()
            return created
        except Exception:
            await session.rollback()
            raise


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish creator partnership worker heartbeat")

            try:
                created = await run_once()
                if created:
                    logger.info("Created %s creator partnership monthly grants", created)
                    await _event(redis, "creator_partnership_grant_success")
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Creator partnership grant pass failed")
                await _event(redis, "creator_partnership_grant_failure")
                await _event(redis, "creator_partnership_worker_loop_error")
            await asyncio.sleep(max(60, settings.creator_partnership_grant_interval_seconds))
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
