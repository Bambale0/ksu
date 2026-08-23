"""server-owned generation action contexts

Revision ID: 0032_generation_action_contexts
Revises: 0031_reference_media_metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_generation_action_contexts"
down_revision: str | None = "0031_reference_media_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_action_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_generation_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_mode", sa.String(length=32), nullable=True),
        sa.Column("target_model_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_count", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'executed', 'expired')",
            name="ck_generation_action_contexts_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_generation_id"], ["generations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generation_action_contexts_user_created",
        "generation_action_contexts",
        ["user_id", "created_at"],
    )
    op.create_index(
        "uq_generation_action_contexts_active",
        "generation_action_contexts",
        ["user_id", "source_generation_id", "action"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_action_contexts_active", table_name="generation_action_contexts")
    op.drop_index("ix_generation_action_contexts_user_created", table_name="generation_action_contexts")
    op.drop_table("generation_action_contexts")