"""add shared admin command and operator domain

Revision ID: 0011_admin_domain
Revises: 0010_notification_delivery
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_admin_domain"
down_revision: str | None = "0010_notification_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "admin_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=96), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_admin_commands_admin_created", "admin_commands", ["admin_user_id", "created_at"])
    op.create_index("ix_admin_commands_action_created", "admin_commands", ["action", "created_at"])
    op.create_index("ix_admin_commands_request_id", "admin_commands", ["request_id"])
    op.create_index("ix_admin_commands_admin_user_id", "admin_commands", ["admin_user_id"])

    op.create_table(
        "tariff_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index("ix_tariff_versions_status_created", "tariff_versions", ["status", "created_at"])

    op.create_table(
        "support_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_message_id", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["support_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_support_outbox_message"),
    )
    op.create_index("ix_support_outbox_ticket_id", "support_outbox", ["ticket_id"])
    op.create_index("ix_support_outbox_status_available", "support_outbox", ["status", "available_at"])
    op.create_index("ix_support_outbox_status_lease", "support_outbox", ["status", "lease_until"])

    op.create_table(
        "cms_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_cms_documents_slug", "cms_documents", ["slug"])

    op.create_table(
        "cms_document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["document_id"], ["cms_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version", name="uq_cms_document_version"),
    )
    op.create_index("ix_cms_document_versions_document_id", "cms_document_versions", ["document_id"])
    op.create_index(
        "ix_cms_document_versions_document_created",
        "cms_document_versions",
        ["document_id", "created_at"],
    )

    op.create_table(
        "notification_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("segment", sa.JSON(), nullable=False),
        sa.Column("message", sa.JSON(), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("started_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["started_by_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_campaigns_status_created", "notification_campaigns", ["status", "created_at"])

    op.create_table(
        "notification_campaign_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_message_id", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["campaign_id"], ["notification_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_notification_campaign_user"),
    )
    op.create_index("ix_notification_campaign_deliveries_campaign_id", "notification_campaign_deliveries", ["campaign_id"])
    op.create_index("ix_notification_campaign_deliveries_user_id", "notification_campaign_deliveries", ["user_id"])
    op.create_index(
        "ix_campaign_delivery_status_available",
        "notification_campaign_deliveries",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_campaign_delivery_status_lease",
        "notification_campaign_deliveries",
        ["status", "lease_until"],
    )

    op.create_table(
        "prompt_library_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("moderated_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("moderation_reason", sa.Text(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moderated_by_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_library_status_created", "prompt_library_items", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_prompt_library_status_created", table_name="prompt_library_items")
    op.drop_table("prompt_library_items")

    op.drop_index("ix_campaign_delivery_status_lease", table_name="notification_campaign_deliveries")
    op.drop_index("ix_campaign_delivery_status_available", table_name="notification_campaign_deliveries")
    op.drop_index("ix_notification_campaign_deliveries_user_id", table_name="notification_campaign_deliveries")
    op.drop_index("ix_notification_campaign_deliveries_campaign_id", table_name="notification_campaign_deliveries")
    op.drop_table("notification_campaign_deliveries")

    op.drop_index("ix_notification_campaigns_status_created", table_name="notification_campaigns")
    op.drop_table("notification_campaigns")

    op.drop_index("ix_cms_document_versions_document_created", table_name="cms_document_versions")
    op.drop_index("ix_cms_document_versions_document_id", table_name="cms_document_versions")
    op.drop_table("cms_document_versions")
    op.drop_index("ix_cms_documents_slug", table_name="cms_documents")
    op.drop_table("cms_documents")

    op.drop_index("ix_support_outbox_status_lease", table_name="support_outbox")
    op.drop_index("ix_support_outbox_status_available", table_name="support_outbox")
    op.drop_index("ix_support_outbox_ticket_id", table_name="support_outbox")
    op.drop_table("support_outbox")

    op.drop_index("ix_tariff_versions_status_created", table_name="tariff_versions")
    op.drop_table("tariff_versions")

    op.drop_index("ix_admin_commands_admin_user_id", table_name="admin_commands")
    op.drop_index("ix_admin_commands_request_id", table_name="admin_commands")
    op.drop_index("ix_admin_commands_action_created", table_name="admin_commands")
    op.drop_index("ix_admin_commands_admin_created", table_name="admin_commands")
    op.drop_table("admin_commands")
