"""add durable Nexus admin tasks

Revision ID: 0036_nexus_admin_tasks
Revises: 0035_generation_integrity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_nexus_admin_tasks"
down_revision: str | None = "0035_generation_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nexus_admin_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
        sa.Column("image_size", sa.String(length=8), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("result_url", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_nexus_admin_tasks_telegram_id", "nexus_admin_tasks", ["telegram_id"])
    op.create_index(
        "ix_nexus_admin_tasks_status_available",
        "nexus_admin_tasks",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_nexus_admin_tasks_external_id",
        "nexus_admin_tasks",
        ["external_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_nexus_admin_tasks_external_id", table_name="nexus_admin_tasks")
    op.drop_index("ix_nexus_admin_tasks_status_available", table_name="nexus_admin_tasks")
    op.drop_index("ix_nexus_admin_tasks_telegram_id", table_name="nexus_admin_tasks")
    op.drop_table("nexus_admin_tasks")
