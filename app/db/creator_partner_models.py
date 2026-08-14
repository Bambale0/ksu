from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CreatorPartnershipApplication(TimestampMixin, Base):
    __tablename__ = "creator_partnership_applications"
    __table_args__ = (
        Index("ix_creator_partnership_app_user_created", "user_id", "created_at"),
        Index("ix_creator_partnership_app_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    audience_size: Mapped[int] = mapped_column(Integer, nullable=False)
    average_views: Mapped[int | None] = mapped_column(Integer)
    cooperation_format: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    decided_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL"), index=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreatorPartnershipAgreement(TimestampMixin, Base):
    __tablename__ = "creator_partnership_agreements"
    __table_args__ = (
        Index("ix_creator_partnership_agreement_status", "status"),
        Index("ix_creator_partnership_agreement_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("creator_partnership_applications.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    terms_summary: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_rox: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    terms: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    approved_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreatorPartnershipGrant(TimestampMixin, Base):
    __tablename__ = "creator_partnership_grants"
    __table_args__ = (
        UniqueConstraint("agreement_id", "period", name="uq_creator_partnership_grant_period"),
        Index("ix_creator_partnership_grant_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("creator_partnership_agreements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    amount_rox: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    wallet_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallet_transactions.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    granted_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(24), default="scheduler", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
