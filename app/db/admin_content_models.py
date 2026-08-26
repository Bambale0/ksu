from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class GenerationModerationState(TimestampMixin, Base):
    __tablename__ = "generation_moderation_state"

    generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(24), default="visible", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    # ``None`` means the creator has marked a publication 18+ and it is waiting
    # in the moderation queue. Once an admin decides, the actor/timestamp are set.
    moderated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
