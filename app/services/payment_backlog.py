"""Privacy-safe, read-only classification for historical payment review."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.db.payment_reconcile_models import PaymentReconcileState
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

    @classmethod
    async def retry_snapshot(
        cls, session: AsyncSession, *, older_than_days: int = 1
    ) -> list[dict[str, object]]:
        """Read-only grouped reconciliation coverage, no invoice/user identifiers.

        The missing-ID Card branch is intentionally excluded from polling;
        other unscheduled rows may simply have no configured provider.
        """
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        now = utcnow()
        poll_state = case(
            (
                and_(
                    Payment.provider == "card",
                    Payment.external_id.is_(None),
                ),
                "manual_card_without_provider_id",
            ),
            (PaymentReconcileState.payment_id.is_(None), "not_scheduled"),
            (PaymentReconcileState.next_attempt_at > now, "waiting"),
            else_="due",
        ).label("poll_state")
        # Avoid exposing a payment identifier, provider invoice, payload,
        # amount or user information. All aggregates are grouped by state.
        query = (
            select(
                Payment.provider,
                Payment.status,
                poll_state,
                func.count(Payment.id).label("count"),
            )
            .outerjoin(
                PaymentReconcileState,
                PaymentReconcileState.payment_id == Payment.id,
            )
            .where(
                Payment.status.in_(cls.OPEN_STATUSES),
                Payment.updated_at < now - timedelta(days=older_than_days),
            )
            .group_by(Payment.provider, Payment.status, poll_state)
            .order_by(Payment.provider, Payment.status, poll_state)
        )
        rows = (await session.execute(query)).all()
        return [
            {
                "provider": provider,
                "status": status,
                "poll_state": state,
                "count": count,
            }
            for provider, status, state, count in rows
        ]

    @classmethod
    async def card_identity_snapshot(
        cls, session: AsyncSession, *, older_than_days: int = 1
    ) -> dict[str, int]:
        """Count collisions among unresolved Card intents without exposing identities.

        Equal buyer email, price and currency are NOT proof that the local
        payment is the same invoice. All grouping stays inside PostgreSQL;
        neither email nor amount is selected into Python or audit output.
        """
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")

        email = func.nullif(
            func.lower(func.trim(Payment.payload["billing_email"].as_string())),
            "",
        )
        rows = (await session.execute(
            select(
                func.count(Payment.id).label("group_size"),
                func.max(case((email.is_(None), 1), else_=0)).label("missing_email"),
            )
            .where(
                Payment.provider == "card",
                Payment.status == "creation_unknown",
                Payment.external_id.is_(None),
                Payment.updated_at < utcnow() - timedelta(days=older_than_days),
            )
            .group_by(email, Payment.amount, Payment.currency)
        )).all()

        group_sizes = [(int(size), bool(missing)) for size, missing in rows]
        return {
            "payment_count": sum(size for size, _ in group_sizes),
            "signature_groups": len(group_sizes),
            "repeated_signature_groups": sum(
                1 for size, _ in group_sizes if size > 1
            ),
            "repeated_signature_payments": sum(
                size for size, _ in group_sizes if size > 1
            ),
            "missing_email_payments": sum(
                size for size, missing in group_sizes if missing
            ),
            "single_signature_payments": sum(
                1 for size, missing in group_sizes if size == 1 and not missing
            ),
        }

    @classmethod
    async def request_snapshot(
        cls, session: AsyncSession, *, older_than_days: int = 1
    ) -> list[dict[str, object]]:
        """Aggregate local creation-request linkage without identifying users.

        Each payment has at most one PaymentRequest (unique payment_id).
        A missing request must NEVER be interpreted as proof no external
        invoice exists; this report performs no provider calls or updates.
        """
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        request_state = case(
            (PaymentRequest.id.is_(None), "missing"),
            else_=PaymentRequest.status,
        ).label("request_state")
        rows = (await session.execute(
            select(
                Payment.provider, Payment.status, request_state,
                func.count(Payment.id).label("count"),
            )
            .outerjoin(PaymentRequest, PaymentRequest.payment_id == Payment.id)
            .where(
                Payment.status.in_(cls.OPEN_STATUSES),
                Payment.updated_at < utcnow() - timedelta(days=older_than_days),
            )
            .group_by(Payment.provider, Payment.status, request_state)
            .order_by(Payment.provider, Payment.status, request_state)
        )).all()
        return [
            {
                "provider": provider,
                "status": status,
                "request_state": state,
                "count": count,
            }
            for provider, status, state, count in rows
        ]
