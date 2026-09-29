"""add durable Seedance admin test tasks

Revision ID: 0042_seedance_admin_tasks
Revises: 0041_partner_referral_terms
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_seedance_admin_tasks"
down_revision: str | None = "0041_partner_referral_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seedance_admin_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_seedance_admin_tasks_telegram_id", "seedance_admin_tasks", ["telegram_id"])
    op.create_index(
        "ix_seedance_admin_tasks_status_available",
        "seedance_admin_tasks",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_seedance_admin_tasks_external_id",
        "seedance_admin_tasks",
        ["external_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_seedance_admin_tasks_external_id", table_name="seedance_admin_tasks")
    op.drop_index("ix_seedance_admin_tasks_status_available", table_name="seedance_admin_tasks")
    op.drop_index("ix_seedance_admin_tasks_telegram_id", table_name="seedance_admin_tasks")
    op.drop_table("seedance_admin_tasks")
