from __future__ import annotations

import logging
import math
import random
import time
from datetime import timedelta

from sqlalchemy import or_, select
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_reconcile_models import PaymentReconcileState
from app.services.payment_retry_schedule import PaymentRetrySchedule
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
    async def run_once(cls, redis: Redis | None = None, *, durable: bool = False) -> int:
        cutoff = utcnow() - timedelta(seconds=settings.payment_reconcile_stale_seconds)
        async with SessionFactory() as session:
            query = select(Payment.id, Payment.provider, Payment.external_id)
            if durable:
                query = query.outerjoin(
                    PaymentReconcileState, PaymentReconcileState.payment_id == Payment.id
                ).add_columns(PaymentReconcileState.attempt_count).where(
                    or_(
                        PaymentReconcileState.payment_id.is_(None),
                        PaymentReconcileState.next_attempt_at <= utcnow(),
                    )
                )
            payments = list(
                (
                    await session.execute(
                        query.where(
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
                        .limit(settings.payment_reconcile_batch_size + len(cls._retry_after))
                    )
                ).all()
            )

        processed = 0
        attempted = 0
        now = time.monotonic()
        for payment_id in list(cls._retry_after):
            if cls._retry_after[payment_id] <= now:
                cls._retry_after.pop(payment_id, None)
        for row in payments:
            payment_id, provider, external_id = row[:3]
            persisted_failures = int(row[3] or 0) if durable else 0
            if cls._retry_after.get(payment_id, 0) > now:
                continue
            if redis is not None:
                try:
                    # Redis survives worker restarts and prevents bursts of
                    # stale provider lookups while a provider is unavailable.
                    if await redis.exists(f"ksu:payment-reconcile:cooldown:{payment_id}"):
                        continue
                except RedisError:
                    # Never block an authoritative payment recovery merely
                    # because the optional shared cooldown store is unavailable.
                    logger.warning("Payment reconciliation shared cooldown unavailable")
            if attempted >= settings.payment_reconcile_batch_size:
                break
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
            attempted += 1
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
                    failures = min(max(cls._failure_counts.get(payment_id, 0), persisted_failures) + 1, 6)
                    if len(cls._failure_counts) >= 10000 and payment_id not in cls._failure_counts:
                        cls._failure_counts.pop(next(iter(cls._failure_counts)))
                    cls._failure_counts[payment_id] = failures
                    delay = min(cls.RETRY_MAX_SECONDS, cls.RETRY_BASE_SECONDS * (2 ** (failures - 1)))
                    cooldown_seconds = min(cls.RETRY_MAX_SECONDS, delay * random.uniform(0.8, 1.2))
                    cls._retry_after[payment_id] = time.monotonic() + cooldown_seconds
                    if redis is not None:
                        try:
                            await redis.set(
                                f"ksu:payment-reconcile:cooldown:{payment_id}",
                                "1",
                                ex=max(1, math.ceil(cooldown_seconds)),
                            )
                        except RedisError:
                            logger.warning("Payment reconciliation shared cooldown write unavailable")
                    logger.exception("Payment reconciliation failed for %s", payment_id)
                    if durable:
                        try:
                            async with SessionFactory() as schedule_session:
                                await PaymentRetrySchedule.record(
                                    schedule_session,
                                    payment_id=payment_id,
                                    attempt_count=failures,
                                    cooldown_seconds=max(1, math.ceil(cooldown_seconds)),
                                    # No provider payload, request URL or exception text.
                                    last_error_code="provider_reconcile_exception",
                                )
                        except Exception:
                            logger.exception("Could not persist payment reconciliation retry schedule")
                else:
                    cls._retry_after.pop(payment_id, None)
                    cls._failure_counts.pop(payment_id, None)
                    processed += 1
                    if durable:
                        # Unchanged old invoices are not terminal; do not hammer
                        # providers every 60s if polling reported no new state.
                        try:
                            async with SessionFactory() as schedule_session:
                                status = await schedule_session.scalar(
                                    select(Payment.status).where(Payment.id == payment_id)
                                )
                                if status in cls.RECONCILABLE_STATUSES:
                                    await PaymentRetrySchedule.record(
                                        schedule_session, payment_id=payment_id,
                                        attempt_count=0, cooldown_seconds=900,
                                    )
                        except Exception:
                            logger.exception("Could not persist unchanged payment polling schedule")
        return processed