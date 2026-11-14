from __future__ import annotations

import logging
import random
import time
from datetime import timedelta

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.models import Payment
from app.db.session import SessionFactory
from app.services.admin_security import utcnow
from app.services.card_payments import CardPaymentService
from app.services.payment_2328 import Payment2328Service
from app.services.payments import PaymentService

logger = logging.getLogger(__name__)


class PaymentReconciliationService:
    # Advisory, process-local cooldown. Webhooks remain authoritative.
    _retry_after: dict[object, float] = {}
    _failure_counts: dict[object, int] = {}
    RETRY_BASE_SECONDS = 60
    RETRY_MAX_SECONDS = 1800

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
                        select(Payment.id, Payment.provider, Payment.external_id)
                        .where(
                            Payment.status.in_(cls.RECONCILABLE_STATUSES),
                            Payment.updated_at < cutoff,
                            # Card intents without a provider invoice id cannot be
                            # recovered by polling. They are intentionally recovered
                            # from an authoritative Lava webhook instead.
                            or_(
                                Payment.provider != CardPaymentService.PROVIDER,
                                Payment.external_id.is_not(None),
                            ),
                        )
                        .order_by(Payment.updated_at.asc())
                        .limit(settings.payment_reconcile_batch_size)
                    )
                ).all()
            )

        processed = 0
        now = time.monotonic()
        for payment_id in list(cls._retry_after):
            if cls._retry_after[payment_id] <= now:
                cls._retry_after.pop(payment_id, None)
        for payment_id, provider, external_id in payments:
            if cls._retry_after.get(payment_id, 0) > now:
                continue
            if provider == CardPaymentService.PROVIDER:
                if not external_id:
                    continue
                if not CardPaymentService.provider_configured():
                    logger.debug(
                        "Skipping card payment reconciliation because provider is not configured"
                    )
                    continue
            elif provider == Payment2328Service.PROVIDER:
                if not Payment2328Service.provider_configured():
                    logger.debug(
                        "Skipping 2328.io payment reconciliation because provider is not configured"
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
                    elif provider == Payment2328Service.PROVIDER:
                        await Payment2328Service.reconcile(session, payment_id=payment_id)
                    else:
                        await PaymentService.reconcile(session, payment_id=payment_id)
                except Exception:
                    # Provider reconciliation is eventually consistent. A temporary
                    # outage must not turn a recoverable payment into failed or create
                    # another invoice.
                    failures = min(cls._failure_counts.get(payment_id, 0) + 1, 6)
                    cls._failure_counts[payment_id] = failures
                    delay = min(cls.RETRY_MAX_SECONDS, cls.RETRY_BASE_SECONDS * (2 ** (failures - 1)))
                    cls._retry_after[payment_id] = time.monotonic() + delay * random.uniform(0.8, 1.2)
                    logger.exception("Payment reconciliation failed for %s", payment_id)
                else:
                    cls._retry_after.pop(payment_id, None)
                    cls._failure_counts.pop(payment_id, None)
                    processed += 1
        return processed
