from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionFactory, engine
from app.services.broadcasts import BroadcastService

logger = logging.getLogger(__name__)


async def run() -> None:
    try:
        while True:
            try:
                async with SessionFactory() as session:
                    created = await BroadcastService.fanout_once(session)
                    await session.commit()
            except Exception:  # noqa: BLE001 - worker must continue after persisted failures
                logger.exception("Broadcast fan-out iteration failed")
                created = 0
            if created:
                continue
            await asyncio.sleep(settings.broadcast_worker_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
