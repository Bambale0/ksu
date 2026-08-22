from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserReference(TimestampMixin, Base):
    __tablename__ = "user_references"
    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video', 'audio')", name="ck_user_references_kind"),
        CheckConstraint("status IN ('ready', 'deleted')", name="ck_user_references_status"),
        UniqueConstraint("user_id", "source_url", name="uq_user_references_user_source"),
        Index("ix_user_references_user_kind_created", "user_id", "kind", "created_at"),
        Index(
            "uq_user_references_user_kind_hash",
            "user_id",
            "kind",
            "file_hash",
            unique=True,
        ),
        Index("ix_user_references_user_kind_last_used", "user_id", "kind", "last_used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ready", nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    container: Mapped[str | None] = mapped_column(String(64))
    video_codec: Mapped[str | None] = mapped_column(String(64))
    audio_codec: Mapped[str | None] = mapped_column(String(64))
    probe_status: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64), default="manual", server_default="manual", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserPreset(TimestampMixin, Base):
    __tablename__ = "user_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_presets_user_name"),
        Index("ix_user_presets_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    billing_seconds: Mapped[int | None] = mapped_column(Integer)
    reference_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
