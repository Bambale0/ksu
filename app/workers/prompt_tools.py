from __future__ import annotations

import asyncio
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import WORKER_LOOP_ERRORS, record_worker_heartbeat
from app.providers.nexus_prompt_tools import cleanup_stale_prompt_frames
from app.db.session import SessionFactory, engine
from app.services.prompt_tools import PromptToolOutboxService, PromptToolProcessor

logger = logging.getLogger(__name__)
WORKER_NAME = "prompt-tool-worker"
WAKE_KEY = "wake:prompt-tools"


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    last_frame_cleanup = 0.0
    try:
        while True:
            now = time.monotonic()
            if now - last_frame_cleanup >= 300:
                try:
                    await asyncio.to_thread(cleanup_stale_prompt_frames)
                except Exception:
                    logger.exception("Could not clean stale Nexus prompt frames")
                last_frame_cleanup = now
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish prompt tool worker heartbeat")

            try:
                async with SessionFactory() as session:
                    claimed = await PromptToolOutboxService.claim(session)
                if claimed is not None:
                    async with SessionFactory() as session:
                        await PromptToolProcessor.process(session, redis, claimed)
                    continue
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Prompt tool worker iteration failed")

            try:
                await redis.blpop(WAKE_KEY, timeout=settings.generation_worker_poll_seconds)
            except RedisError:
                await asyncio.sleep(settings.generation_worker_poll_seconds)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
