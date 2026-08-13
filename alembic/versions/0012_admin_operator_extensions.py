"""add admin operator extensions

Revision ID: 0012_admin_operator_extensions
Revises: 0011_admin_domain
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_admin_operator_extensions"
down_revision: str | None = "0011_admin_domain"
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
        "support_ticket_admin_state",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_admin_id", sa.Uuid(), nullable=True),
        sa.Column("priority", sa.String(length=24), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("ticket_id"),
    )
    op.create_index(
        "ix_support_ticket_admin_state_assigned_admin_id",
        "support_ticket_admin_state",
        ["assigned_admin_id"],
    )

    op.create_table(
        "admin_runtime_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by_admin_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["updated_by_admin_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "admin_trends",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("admin_trends")
    op.drop_table("admin_runtime_settings")
    op.drop_index(
        "ix_support_ticket_admin_state_assigned_admin_id",
        table_name="support_ticket_admin_state",
    )
    op.drop_table("support_ticket_admin_state")
