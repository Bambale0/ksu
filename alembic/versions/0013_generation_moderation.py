"""add explicit generation moderation state

Revision ID: 0013_generation_moderation
Revises: 0012_admin_operator_extensions
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_generation_moderation"
down_revision: str | None = "0012_admin_operator_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_moderation_state",
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moderated_by_admin_id", sa.Uuid(), nullable=False),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["moderated_by_admin_id"],
            ["admin_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("generation_id"),
    )


def downgrade() -> None:
    op.drop_table("generation_moderation_state")
