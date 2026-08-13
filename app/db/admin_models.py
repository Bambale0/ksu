from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AdminCommand(TimestampMixin, Base):
    """Append-only command ledger for privileged write operations."""

    __tablename__ = "admin_commands"
    __table_args__ = (
        Index("ix_admin_commands_admin_created", "admin_user_id", "created_at"),
        Index("ix_admin_commands_action_created", "action", "created_at"),
        Index("ix_admin_commands_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(96), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="reserved", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TariffVersion(TimestampMixin, Base):
    __tablename__ = "tariff_versions"
    __table_args__ = (Index("ix_tariff_versions_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    published_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportOutbox(TimestampMixin, Base):
    __tablename__ = "support_outbox"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_support_outbox_message"),
        Index("ix_support_outbox_status_available", "status", "available_at"),
        Index("ix_support_outbox_status_lease", "status", "lease_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_messages.id", ondelete="CASCADE"), nullable=False
    )
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_message_id: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text)


class SupportTicketAdminState(TimestampMixin, Base):
    __tablename__ = "support_ticket_admin_state"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL"), index=True
    )
    priority: Mapped[str] = mapped_column(String(24), default="normal", nullable=False)


class CmsDocument(TimestampMixin, Base):
    __tablename__ = "cms_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)


class CmsDocumentVersion(TimestampMixin, Base):
    __tablename__ = "cms_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_cms_document_version"),
        Index("ix_cms_document_versions_document_created", "document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cms_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    published_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationCampaign(TimestampMixin, Base):
    __tablename__ = "notification_campaigns"
    __table_args__ = (Index("ix_notification_campaigns_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    channel: Mapped[str] = mapped_column(String(24), default="telegram", nullable=False)
    segment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    message: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    started_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationCampaignDelivery(TimestampMixin, Base):
    __tablename__ = "notification_campaign_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_notification_campaign_user"),
        Index("ix_campaign_delivery_status_available", "status", "available_at"),
        Index("ix_campaign_delivery_status_lease", "status", "lease_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_message_id: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text)


class PromptLibraryItem(TimestampMixin, Base):
    __tablename__ = "prompt_library_items"
    __table_args__ = (Index("ix_prompt_library_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    moderated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="SET NULL")
    )
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminRuntimeSetting(TimestampMixin, Base):
    __tablename__ = "admin_runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )


class AdminTrend(TimestampMixin, Base):
    __tablename__ = "admin_trends"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False
    )
