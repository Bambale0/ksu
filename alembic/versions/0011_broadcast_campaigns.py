"""add permissioned marketing broadcast campaigns

Revision ID: 0011_broadcast_campaigns
Revises: 0010_notification_delivery
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_broadcast_campaigns"
down_revision: str | None = "0010_notification_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broadcast_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("audience_json", sa.JSON(), nullable=False),
        sa.Column("cursor_user_id", sa.Uuid(), nullable=True),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fanout_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcast_campaigns_created_by_admin_id", "broadcast_campaigns", ["created_by_admin_id"], unique=False)
    op.create_index("ix_broadcast_campaign_status_created", "broadcast_campaigns", ["status", "created_at"], unique=False)

    op.create_table(
        "broadcast_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["broadcast_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_broadcast_campaign_user"),
    )
    op.create_index("ix_broadcast_recipients_campaign_id", "broadcast_recipients", ["campaign_id"], unique=False)
    op.create_index("ix_broadcast_recipients_notification_id", "broadcast_recipients", ["notification_id"], unique=False)
    op.create_index("ix_broadcast_recipients_user_id", "broadcast_recipients", ["user_id"], unique=False)
    op.create_index("ix_broadcast_recipient_campaign_created", "broadcast_recipients", ["campaign_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_broadcast_recipient_campaign_created", table_name="broadcast_recipients")
    op.drop_index("ix_broadcast_recipients_user_id", table_name="broadcast_recipients")
    op.drop_index("ix_broadcast_recipients_notification_id", table_name="broadcast_recipients")
    op.drop_index("ix_broadcast_recipients_campaign_id", table_name="broadcast_recipients")
    op.drop_table("broadcast_recipients")
    op.drop_index("ix_broadcast_campaign_status_created", table_name="broadcast_campaigns")
    op.drop_index("ix_broadcast_campaigns_created_by_admin_id", table_name="broadcast_campaigns")
    op.drop_table("broadcast_campaigns")
