from __future__ import annotations

import asyncio
import logging
import time

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
from app.services.media_assets import MediaIngestService
from app.services.media_legacy_backfill import LegacyMediaBackfillService
from app.services.music_media import MusicMediaIngestService

logger = logging.getLogger(__name__)
WORKER_NAME = "media-worker"


async def _event(redis: Redis, name: str) -> None:
    try:
        await record_distributed_event(redis, name)
    except Exception:
        logger.exception("Could not record distributed event %s", name)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    next_legacy_reconcile_at = 0.0
    try:
        while True:
            try:
                await record_worker_heartbeat(redis, WORKER_NAME)
            except RedisError:
                logger.warning("Could not publish media worker heartbeat")

            now = time.monotonic()
            if now >= next_legacy_reconcile_at:
                try:
                    async with SessionFactory() as session:
                        await LegacyMediaBackfillService.ensure(session)
                except Exception:
                    WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                    logger.exception("Legacy media reconciliation failed")
                    await _event(redis, "media_reconcile_failure")
                next_legacy_reconcile_at = now + settings.media_legacy_reconcile_seconds

            processed = False
            try:
                async with SessionFactory() as session:
                    processed = await MusicMediaIngestService.process_one(session)
                if processed:
                    await _event(redis, "music_audio_ingest_processed")
            except Exception:
                WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                logger.exception("Music audio ingest worker iteration failed")
                await _event(redis, "music_audio_worker_loop_error")

            if not processed:
                try:
                    async with SessionFactory() as session:
                        processed = await MediaIngestService.process_one(session)
                except Exception:
                    WORKER_LOOP_ERRORS.labels(worker=WORKER_NAME).inc()
                    logger.exception("Media ingest worker iteration failed")
                    await _event(redis, "media_worker_loop_error")
                    processed = False

            if processed:
                await _event(redis, "media_ingest_processed")
                continue
            await asyncio.sleep(settings.media_worker_poll_seconds)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
