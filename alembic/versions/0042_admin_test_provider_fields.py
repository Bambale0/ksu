"""generalize durable admin test tasks for Seedance

Revision ID: 0042_admin_test_provider_fields
Revises: 0041_partner_referral_terms
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_admin_test_provider_fields"
down_revision: str | None = "0041_partner_referral_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nexus_admin_tasks",
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="nexus"),
    )
    op.add_column(
        "nexus_admin_tasks",
        sa.Column(
            "model_id",
            sa.String(length=64),
            nullable=False,
            server_default="nano-banana-pro",
        ),
    )
    op.add_column(
        "nexus_admin_tasks",
        sa.Column(
            "parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("nexus_admin_tasks", "parameters")
    op.drop_column("nexus_admin_tasks", "model_id")
    op.drop_column("nexus_admin_tasks", "provider")
