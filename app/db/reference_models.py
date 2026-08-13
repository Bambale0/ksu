from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserReference(TimestampMixin, Base):
    __tablename__ = "user_references"
    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video', 'audio')", name="ck_user_references_kind"),
        CheckConstraint("status IN ('ready', 'deleted')", name="ck_user_references_status"),
        UniqueConstraint("user_id", "sha256", name="uq_user_references_user_sha256"),
        Index("ix_user_references_user_kind_created", "user_id", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ready", nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    etag: Mapped[str | None] = mapped_column(String(255))
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
    reference_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
