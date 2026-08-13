from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PromptToolTask(TimestampMixin, Base):
    __tablename__ = "prompt_tool_tasks"
    __table_args__ = (
        CheckConstraint(
            "tool IN ('image_analysis', 'prompt_builder')",
            name="ck_prompt_tool_tasks_tool",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'succeeded', 'failed')",
            name="ck_prompt_tool_tasks_status",
        ),
        Index("ix_prompt_tool_tasks_user_created", "user_id", "created_at"),
        Index("ix_prompt_tool_tasks_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tool: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="kie", nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cost_credits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    provider_credits: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromptToolOutbox(TimestampMixin, Base):
    __tablename__ = "prompt_tool_outbox"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_prompt_tool_outbox_task"),
        Index("ix_prompt_tool_outbox_claim", "status", "available_at", "created_at"),
        Index("ix_prompt_tool_outbox_lease", "status", "lease_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_tool_tasks.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
