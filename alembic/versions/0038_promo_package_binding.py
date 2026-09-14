"""bind promo campaigns to payment packages

Revision ID: 0038_promo_package_binding
Revises: 0037_promo_paid_bonuses
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_promo_package_binding"
down_revision: str | None = "0037_promo_paid_bonuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column("package_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "promo_codes",
        sa.Column(
            "min_base_credits",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_promo_codes_min_base_credits",
        "promo_codes",
        "min_base_credits >= 0",
    )
    op.create_index(
        "ix_promo_codes_package_active",
        "promo_codes",
        ["package_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_promo_codes_package_active", table_name="promo_codes")
    op.drop_constraint(
        "ck_promo_codes_min_base_credits",
        "promo_codes",
        type_="check",
    )
    op.drop_column("promo_codes", "min_base_credits")
    op.drop_column("promo_codes", "package_id")
