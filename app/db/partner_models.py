from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PartnerApplication(TimestampMixin, Base):
    __tablename__ = "partner_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','suspended')",
            name="ck_partner_applications_status",
        ),
        UniqueConstraint("user_id", name="uq_partner_applications_user"),
        Index("ix_partner_applications_status_updated", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    terms_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL"), index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    application_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PartnerApplicationEvent(Base):
    __tablename__ = "partner_application_events"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('pending','approved','rejected','suspended')",
            name="ck_partner_application_events_to_status",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending','approved','rejected','suspended')",
            name="ck_partner_application_events_from_status",
        ),
        CheckConstraint(
            "actor_type IN ('user','admin','system')",
            name="ck_partner_application_events_actor_type",
        ),
        Index("ix_partner_application_events_application_created", "application_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
