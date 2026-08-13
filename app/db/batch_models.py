from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BatchGenerationJob(TimestampMixin, Base):
    __tablename__ = "batch_generation_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running','partial','succeeded','failed')", name="ck_batch_generation_jobs_status"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_batch_generation_jobs_user_idempotency"),
        Index("ix_batch_generation_jobs_user_created", "user_id", "created_at"),
        Index("ix_batch_generation_jobs_status_updated", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    billing_seconds: Mapped[int | None] = mapped_column(Integer)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initial_cost_rox: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_charged_rox: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchGenerationItem(TimestampMixin, Base):
    __tablename__ = "batch_generation_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_batch_generation_items_ordinal"),
        UniqueConstraint("generation_id", name="uq_batch_generation_items_generation"),
        Index("ix_batch_generation_items_batch_ordinal", "batch_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batch_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    input_url: Mapped[str] = mapped_column(Text, nullable=False)
    generation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generations.id", ondelete="RESTRICT"), nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BatchGenerationCommand(TimestampMixin, Base):
    __tablename__ = "batch_generation_commands"
    __table_args__ = (
        CheckConstraint("kind IN ('retry_failed')", name="ck_batch_generation_commands_kind"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_batch_generation_commands_user_idempotency"),
        Index("ix_batch_generation_commands_batch_created", "batch_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batch_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_generation_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
