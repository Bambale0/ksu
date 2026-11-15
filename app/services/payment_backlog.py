"""Privacy-safe, read-only classification for historical payment review."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.admin_security import utcnow


class PaymentBacklogReport:
    OPEN_STATUSES = ("creating", "creation_unknown", "pending", "refund_review")

    @classmethod
    async def snapshot(cls, session: AsyncSession, *, older_than_days: int = 1) -> list[dict[str, object]]:
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        threshold = utcnow() - timedelta(days=older_than_days)
        rows = (await session.execute(
            select(
                Payment.provider,
                Payment.status,
                case((Payment.external_id.is_(None), "missing"), else_="present").label("provider_id"),
                func.count(Payment.id).label("count"),
            )
            .where(
                Payment.status.in_(cls.OPEN_STATUSES),
                Payment.updated_at < threshold,
            )
            .group_by(Payment.provider, Payment.status, "provider_id")
            .order_by(Payment.provider, Payment.status, "provider_id")
        )).all()
        # No user IDs, invoice IDs, amounts, tokens or provider payloads.
        return [
            {"provider": provider, "status": status, "provider_id": provider_id, "count": count}
            for provider, status, provider_id, count in rows
        ]