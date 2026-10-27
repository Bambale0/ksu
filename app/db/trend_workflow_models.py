from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TrendWorkflowRun(TimestampMixin, Base):
    __tablename__ = "trend_workflow_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "trend_id", "command_key", name="uq_trend_workflow_start_command"),
        Index("ix_trend_workflow_runs_user_created", "user_id", "created_at"),
        Index("ix_trend_workflow_runs_trend_status", "trend_id", "status"),
        CheckConstraint(
            "status IN ('created', 'running', 'step1_ready', 'completed', 'failed')",
            name="ck_trend_workflow_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    trend_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_trends.id", ondelete="RESTRICT"), nullable=False
    )
    recipe_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    recipe_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="created")
    command_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_incremented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TrendWorkflowStep(TimestampMixin, Base):
    __tablename__ = "trend_workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_key", name="uq_trend_workflow_step_key"),
        UniqueConstraint("workflow_id", "ordinal", name="uq_trend_workflow_step_ordinal"),
        Index("ix_trend_workflow_steps_generation", "generation_id"),
        Index("ix_trend_workflow_steps_asset", "media_asset_id"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'ready', 'completed', 'failed')",
            name="ck_trend_workflow_step_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trend_workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generations.id", ondelete="SET NULL")
    )
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    command_key: Mapped[str | None] = mapped_column(String(160))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    reserved_generation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    attempt_history: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
