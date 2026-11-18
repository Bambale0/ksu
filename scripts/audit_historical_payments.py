"""Read-only operator audit: python -m scripts.audit_historical_payments.

Prints aggregate counts only. It does not settle, retry, or write payments.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from app.services.card_payments import CardPaymentService
from app.services.payment_2328 import Payment2328Service
from app.services.payment_backlog import PaymentBacklogReport
from app.services.payments import PaymentService



def provider_readiness_snapshot() -> dict[str, dict[str, bool]]:
    """Only configuration presence; never read or return credential values."""
    return {
        "2328": {"configured": bool(Payment2328Service.provider_configured())},
        "card": {"configured": bool(CardPaymentService.provider_configured())},
        "cryptobot": {"configured": bool(PaymentService.provider_configured("cryptobot"))},
        "tbank": {"configured": bool(PaymentService.provider_configured("tbank"))},
        "yookassa": {"configured": bool(PaymentService.provider_configured("yookassa"))},
    }


async def main() -> None:
    try:
        async with SessionFactory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            rows = await PaymentBacklogReport.snapshot(session)
            retry_rows = await PaymentBacklogReport.retry_snapshot(session)
            request_rows = await PaymentBacklogReport.request_snapshot(session)
            card_identity = await PaymentBacklogReport.card_identity_snapshot(session)
            review_priorities = await PaymentBacklogReport.review_priority_snapshot(session)
            print(json.dumps({
                "older_than_days": 1,
                "provider_polling_availability": provider_readiness_snapshot(),
                "groups": rows,
                "retry_schedule_groups": retry_rows,
                "creation_request_groups": request_rows,
                "card_identity_ambiguity": card_identity,
                "evidence_gated_review_priorities": review_priorities,
            }, ensure_ascii=False))
            await session.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())