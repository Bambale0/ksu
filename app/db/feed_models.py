from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeedComment(Base):
    __tablename__ = "feed_comments"
    __table_args__ = (
        CheckConstraint("surface IN ('feed', 'profile')", name="ck_feed_comments_surface"),
        Index("ix_feed_comments_generation_surface_created", "generation_id", "surface", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    surface: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeedRemixEvent(Base):
    __tablename__ = "feed_remix_events"
    __table_args__ = (
        UniqueConstraint(
            "source_generation_id",
            "remix_generation_id",
            name="uq_feed_remix_source_result",
        ),
        Index("ix_feed_remix_source_created", "source_generation_id", "created_at"),
        Index("ix_feed_remix_author_created", "remix_author_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    remix_generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    source_author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    remix_author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    credits_spent: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
