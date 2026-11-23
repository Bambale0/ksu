"""Verified non-Telegram identities tied to the canonical users.id/wallet."""
from __future__ import annotations

import uuid
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WebIdentity(TimestampMixin, Base):
    __tablename__ = "web_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_web_identity_provider_subject"),
        UniqueConstraint("provider", "user_id", name="uq_web_identity_provider_user"),
        Index("ix_web_identities_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(320), nullable=False)
    display_email: Mapped[str | None] = mapped_column(String(320))
