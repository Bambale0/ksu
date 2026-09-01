from __future__ import annotations

import asyncio
import logging
import sys

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import record_worker_heartbeat

logger = logging.getLogger(__name__)


async def run(worker_name: str) -> None:
    name = worker_name.strip()
    if not name:
        raise ValueError("Worker name is required")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    interval = max(5, min(30, max(1, settings.worker_stale_after_seconds // 3)))
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, name)
            except RedisError:
                logger.warning("Could not publish %s heartbeat", name)
            await asyncio.sleep(interval)
    finally:
        await redis.aclose()


def main() -> None:
    configure_logging()
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.workers.heartbeat <worker-name>")
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
