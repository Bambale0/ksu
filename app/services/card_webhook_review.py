"""Durable event awareness only: never perform a refund or ROX mutation."""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.card_webhook_review_models import CardWebhookEventReview


class CardWebhookReviewService:
    REVIEW_EVENTS = frozenset({"refund.success", "chargeback.initiated"})

    @classmethod
    async def record(
        cls,
        session: AsyncSession,
        *,
        event_type: str,
        event_id: str,
    ) -> bool:
        """Persist only event type and SHA-256 event ID, once across retries.

        The provider's published event payload does not include an invoice ID.
        Never infer the linked payment from email, price, product, or timestamps.
        """
        if event_type not in cls.REVIEW_EVENTS:
            raise ValueError("Unsupported card webhook event type")
        try:
            canonical_id = str(uuid.UUID(event_id.strip()))
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid provider webhook event UUID") from exc
        event_hash = hashlib.sha256(canonical_id.encode("ascii")).hexdigest()

        stmt = (
            insert(CardWebhookEventReview)
            .values(
                event_id_hash=event_hash,
                event_type=event_type,
                status="manual_review",
            )
            .on_conflict_do_nothing(
                index_elements=[CardWebhookEventReview.event_id_hash],
            )
            .returning(CardWebhookEventReview.event_id_hash)
        )
        inserted = (await session.execute(stmt)).scalar_one_or_none() is not None
        await session.commit()
        return inserted

    @staticmethod
    async def snapshot(session: AsyncSession) -> list[dict[str, object]]:
        """Return aggregated manual-review counts only; no event identifiers."""
        rows = (await session.execute(
            select(
                CardWebhookEventReview.event_type,
                CardWebhookEventReview.status,
                func.count().label("count"),
            )
            .group_by(CardWebhookEventReview.event_type, CardWebhookEventReview.status)
            .order_by(CardWebhookEventReview.event_type, CardWebhookEventReview.status)
        )).all()
        return [
            {"event_type": event_type, "status": status, "count": count}
            for event_type, status, count in rows
        ]
