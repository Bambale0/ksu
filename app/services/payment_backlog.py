"""Privacy-safe, read-only classification for historical payment review."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.admin_security import utcnow


class PaymentBacklogReport:
    OPEN_STATUSES = ("creating", "creation_unknown", "pending", "refund_review")

    @staticmethod
    def _review_route(provider: str, status: str, provider_id: str) -> str:
        """Categorize evidence needed; never infer settlement or refund."""
        if status == "refund_review":
            return "refund_evidence_review"
        if provider_id == "missing":
            if provider == "card":
                return "manual_webhook_evidence_review"
            if provider == "cryptobot":
                return "provider_payload_recovery_review"
            return "manual_provider_evidence_review"
        return "authoritative_provider_status_check"

    @classmethod
    async def snapshot(
        cls, session: AsyncSession, *, older_than_days: int = 1
    ) -> list[dict[str, object]]:
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        now = utcnow()
        threshold = now - timedelta(days=older_than_days)
        age_band = case(
            (Payment.updated_at < now - timedelta(days=30), "30d_plus"),
            (Payment.updated_at < now - timedelta(days=7), "7_to_30d"),
            else_="1_to_7d",
        ).label("age_band")
        provider_id = case(
            (Payment.external_id.is_(None), "missing"), else_="present"
        ).label("provider_id")
        rows = (await session.execute(
            select(
                Payment.provider, Payment.status, provider_id,
                age_band, func.count(Payment.id).label("count"),
            )
            .where(
                Payment.status.in_(cls.OPEN_STATUSES),
                Payment.updated_at < threshold,
            )
            .group_by(Payment.provider, Payment.status, provider_id, age_band)
            .order_by(Payment.provider, Payment.status, provider_id, age_band)
        )).all()
        # Only aggregate metadata: no user IDs, invoice IDs, amounts, or payloads.
        return [
            {
                "provider": provider,
                "status": status,
                "provider_id": id_presence,
                "age_band": band,
                "review_route": cls._review_route(provider, status, id_presence),
                "count": count,
            }
            for provider, status, id_presence, band, count in rows
        ]