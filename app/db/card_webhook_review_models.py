"""Minimal, privacy-safe audit for Lava Top refund/chargeback notifications."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CardWebhookEventReview(Base):
    """No invoice, email, customer, amount, secret or raw event payload stored."""

    __tablename__ = "card_webhook_event_reviews"
    __table_args__ = (
        Index(
            "ix_card_webhook_event_reviews_status_seen",
            "status",
            "first_seen_at",
        ),
    )

    # SHA-256 of the provider event UUID, so repeated webhook deliveries are
    # idempotent without persisting the external opaque event identifier.
    event_id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="manual_review", server_default="manual_review", nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
