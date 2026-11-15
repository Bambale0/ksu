"""Read-only operator audit: python -m scripts.audit_historical_payments.

Prints aggregate counts only. It does not settle, retry, or write payments.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from app.services.payment_backlog import PaymentBacklogReport


async def main() -> None:
    try:
        async with SessionFactory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = await PaymentBacklogReport.snapshot(session)
            retry_rows = await PaymentBacklogReport.retry_snapshot(session)
            print(json.dumps({
                "older_than_days": 1,
                "groups": rows,
                "retry_schedule_groups": retry_rows,
            }, ensure_ascii=False))
            await session.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())