from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PaymentRequest(TimestampMixin, Base):
    """Idempotency record for one user payment-creation intent."""

    __tablename__ = "payment_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_payment_request_user_key"),
        Index("ix_payment_requests_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="creating", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class PaymentReversal(Base):
    """Immutable local accounting record for a provider refund/reversal."""

    __tablename__ = "payment_reversals"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_reversal_idempotency"),
        Index("ix_payment_reversals_payment_created", "payment_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    credits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReferralRewardReversal(Base):
    """Immutable reduction of an accrued referral reward after payment reversal."""

    __tablename__ = "referral_reward_reversals"
    __table_args__ = (
        UniqueConstraint("reward_id", "payment_reversal_id", name="uq_reward_payment_reversal"),
        Index("ix_reward_reversals_reward", "reward_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reward_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("referral_rewards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_reversal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_reversals.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
