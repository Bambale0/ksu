from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import engine
from app.services.payment_reconciliation import PaymentReconciliationService

logger = logging.getLogger(__name__)


async def run() -> None:
    try:
        while True:
            try:
                processed = await PaymentReconciliationService.run_once()
                if processed:
                    logger.info("Reconciled %s payments", processed)
            except Exception:
                logger.exception("Payment reconciliation pass failed")
            await asyncio.sleep(settings.payment_reconcile_interval_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
