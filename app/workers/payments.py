from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.observability import (
    WORKER_LOOP_ERRORS,
    record_distributed_event,
    record_worker_heartbeat,
)
from app.db.session import engine
from app.services.payment_reconciliation import PaymentReconciliationService

logger = logging.getLogger(__name__)
WORKER_NAME = "payment-worker"


async def _event(redis: Redis, name: str) -> None:
    try:
        await record_distributed_event(redis, name)
    except Exception:
        logger.exception("Could not record distributed event %s", name)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish payment worker heartbeat")

            try:
                processed = await PaymentReconciliationService.run_once()
                if processed:
                    logger.info("Reconciled %s payments", processed)
                    await _event(redis, "payment_reconcile_success")
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Payment reconciliation pass failed")
                await _event(redis, "payment_reconcile_failure")
                await _event(redis, "payment_worker_loop_error")
            await asyncio.sleep(settings.payment_reconcile_interval_seconds)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
