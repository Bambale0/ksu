"""Persist only retry scheduling metadata; never decide whether payment settled.

The provider webhook and existing payment services remain authoritative.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.payment_reconcile_models import PaymentReconcileState
from app.services.admin_security import utcnow

logger = logging.getLogger(__name__)


class PaymentRetrySchedule:
    @staticmethod
    async def record(
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        attempt_count: int,
        cooldown_seconds: int,
        last_error_code: str | None = None,
    ) -> None:
        if not 0 <= attempt_count <= 1000:
            raise ValueError("Invalid attempt count")
        if not 1 <= cooldown_seconds <= 86400:
            raise ValueError("Invalid payment retry delay")
        if last_error_code is not None and (
            len(last_error_code) > 64 or not last_error_code.replace("_", "").isalnum()
        ):
            raise ValueError("Invalid retry error category")
        now = utcnow()
        stmt = insert(PaymentReconcileState).values(
            payment_id=payment_id,
            attempt_count=attempt_count,
            last_attempt_at=now,
            next_attempt_at=now + timedelta(seconds=cooldown_seconds),
            last_error_code=last_error_code,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[PaymentReconcileState.payment_id],
            set_={
                "attempt_count": attempt_count,
                "last_attempt_at": now,
                "next_attempt_at": now + timedelta(seconds=cooldown_seconds),
                "last_error_code": last_error_code,
            },
        )
        await session.execute(stmt)
        await session.commit()