from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferralEvent(Base):
    """Durable audit record for every referral admission attempt on registration."""

    __tablename__ = "referral_events"
    __table_args__ = (
        Index("ix_referral_events_inviter_created", "inviter_user_id", "created_at"),
        Index("ix_referral_events_visitor_created", "visitor_user_id", "created_at"),
        Index("ix_referral_events_reason_created", "reason", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visitor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    visitor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inviter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    inviter_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    attached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
