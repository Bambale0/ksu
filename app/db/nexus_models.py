from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NexusAdminTask(TimestampMixin, Base):
    __tablename__ = "nexus_admin_tasks"
    __table_args__ = (
        Index("ix_nexus_admin_tasks_status_available", "status", "available_at"),
        Index("ix_nexus_admin_tasks_external_id", "external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False)
    image_size: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    result_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
