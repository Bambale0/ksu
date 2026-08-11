from __future__ import annotations

import asyncio
import json
import logging
import uuid

from redis.asyncio import Redis

from app.core.config import settings
from app.db.session import SessionFactory, engine
from app.services.generation_provider import GenerationProviderService
from app.services.generations import GenerationService

logger = logging.getLogger(__name__)


async def run() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            item = await redis.blpop(GenerationService.QUEUE_KEY, timeout=5)
            if item is None:
                continue
            _, raw = item
            try:
                payload = json.loads(raw)
                generation_id = uuid.UUID(str(payload["generation_id"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                logger.exception("Dropping malformed generation queue item: %r", raw)
                continue

            async with SessionFactory() as session:
                try:
                    await GenerationProviderService.submit_kie(session, generation_id)
                except Exception:
                    logger.exception("Generation submission failed: %s", generation_id)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
