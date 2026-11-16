"""Read-only overview of Lava Top refunds and chargeback events.

Never prints event IDs or provider/customer payloads.
Usage: python -m scripts.audit_card_webhook_reviews
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from app.services.card_webhook_review import CardWebhookReviewService


async def main() -> None:
    try:
        async with SessionFactory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = await CardWebhookReviewService.snapshot(session)
            print(json.dumps({"card_webhook_event_reviews": rows}, ensure_ascii=False))
            await session.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
