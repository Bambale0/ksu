from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import record_worker_heartbeat

logger = logging.getLogger(__name__)


async def _heartbeat_loop(worker_name: str) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    interval = max(5.0, min(30.0, settings.worker_stale_after_seconds / 3))
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, worker_name)
            except RedisError:
                logger.warning("Could not publish %s heartbeat", worker_name)
            await asyncio.sleep(interval)
    finally:
        await redis.aclose()


async def run_with_heartbeat(
    worker_name: str,
    worker_run: Callable[[], Awaitable[None]],
) -> None:
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(worker_name),
        name=f"{worker_name}-heartbeat",
    )
    worker_task = asyncio.create_task(worker_run(), name=worker_name)
    try:
        done, _ = await asyncio.wait(
            {heartbeat_task, worker_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        first = next(iter(done))
        # A heartbeat task should never end while the worker is alive. Treat that
        # as a fatal runtime failure so Docker restarts the service instead of
        # leaving production falsely healthy/unobservable.
        await first
        if first is heartbeat_task and not worker_task.done():
            raise RuntimeError(f"Heartbeat loop stopped for {worker_name}")
        await worker_task
    finally:
        for task in (worker_task, heartbeat_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(worker_task, heartbeat_task, return_exceptions=True)


def _load_run(module_name: str) -> Callable[[], Awaitable[None]]:
    module = importlib.import_module(module_name)
    run = getattr(module, "run", None)
    if run is None or not callable(run):
        raise RuntimeError(f"{module_name} does not expose async run()")
    return run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("worker_name")
    parser.add_argument("module")
    args = parser.parse_args()
    configure_logging()
    asyncio.run(run_with_heartbeat(args.worker_name, _load_run(args.module)))


if __name__ == "__main__":
    main()
