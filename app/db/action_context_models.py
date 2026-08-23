from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class GenerationActionContext(TimestampMixin, Base):
    """Server-owned snapshot of a post-generation action.

    Buttons under a completed result no longer have to embed or guess all the
    prefilled state in the Mini App URL. A context row captures, at creation
    time, the exact payload the Mini App needs to restore the action screen:
    source generation, action, prefilled defaults, references, source media
    and the eligible model candidates. The row is owner-scoped and expires,
    so an action can never be replayed forever from an old deep link.
    """

    __tablename__ = "generation_action_contexts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'executed', 'expired')",
            name="ck_generation_action_contexts_status",
        ),
        Index("ix_generation_action_contexts_user_created", "user_id", "created_at"),
        Index(
            "uq_generation_action_contexts_active",
            "user_id",
            "source_generation_id",
            "action",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_mode: Mapped[str | None] = mapped_column(String(32))
    target_model_id: Mapped[str | None] = mapped_column(String(128))
    # Full restore payload: the same shape as GET /generations/{id}/action-context
    # so the Mini App can mount the exact prefilled screen without touching the
    # live generation state again.
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    opened_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)