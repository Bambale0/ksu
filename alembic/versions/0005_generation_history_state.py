"""add generation history presentation state

Revision ID: 0005_generation_history_state
Revises: 0004_payment_lifecycle
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_generation_history_state"
down_revision: str | None = "0004_payment_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_history_states",
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("generation_id"),
    )
    op.create_index(
        "ix_generation_history_states_user_id",
        "generation_history_states",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_history_user_hidden",
        "generation_history_states",
        ["user_id", "hidden_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generation_history_user_hidden", table_name="generation_history_states")
    op.drop_index("ix_generation_history_states_user_id", table_name="generation_history_states")
    op.drop_table("generation_history_states")
