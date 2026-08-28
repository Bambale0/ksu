from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Payment
from app.db.session import SessionFactory
from app.services.admin_security import utcnow
from app.services.card_payments import CardPaymentService
from app.services.payments import PaymentService

logger = logging.getLogger(__name__)


class PaymentReconciliationService:
    RECONCILABLE_STATUSES = frozenset(
        {
            "creating",
            "creation_unknown",
            "pending",
            "refund_review",
        }
    )

    @classmethod
    async def run_once(cls) -> int:
        cutoff = utcnow() - timedelta(seconds=settings.payment_reconcile_stale_seconds)
        async with SessionFactory() as session:
            payments = list(
                (
                    await session.execute(
                        select(Payment.id, Payment.provider)
                        .where(
                            Payment.status.in_(cls.RECONCILABLE_STATUSES),
                            Payment.updated_at < cutoff,
                        )
                        .order_by(Payment.updated_at.asc())
                        .limit(settings.payment_reconcile_batch_size)
                    )
                ).all()
            )

        processed = 0
        for payment_id, provider in payments:
            if provider == CardPaymentService.PROVIDER:
                if not CardPaymentService.provider_configured():
                    logger.debug(
                        "Skipping card payment reconciliation because provider is not configured"
                    )
                    continue
            elif not PaymentService.provider_configured(str(provider)):
                logger.debug(
                    "Skipping %s payment reconciliation because provider is not configured",
                    provider,
                )
                continue
            async with SessionFactory() as session:
                try:
                    if provider == CardPaymentService.PROVIDER:
                        await CardPaymentService.reconcile(session, payment_id=payment_id)
                    else:
                        await PaymentService.reconcile(session, payment_id=payment_id)
                except Exception:
                    # Provider reconciliation is eventually consistent. A temporary
                    # outage must not turn a recoverable payment into failed or create
                    # another invoice.
                    logger.exception("Payment reconciliation failed for %s", payment_id)
                else:
                    processed += 1
        return processed
