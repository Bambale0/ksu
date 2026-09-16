"""add partner promo user top-up bonus settings

Revision ID: 0039_promo_user_topup_bonus
Revises: 0038_partner_promo_program
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_promo_user_topup_bonus"
down_revision: str | None = "0038_partner_promo_program"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partner_promo_program_config",
        sa.Column(
            "topup_user_rox",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("50"),
        ),
    )
    op.add_column(
        "partner_promo_program_config",
        sa.Column(
            "topup_user_min_rub",
            sa.Numeric(18, 2),
            nullable=False,
            server_default=sa.text("1000"),
        ),
    )
    op.create_check_constraint(
        "ck_partner_promo_topup_user_nonnegative",
        "partner_promo_program_config",
        "topup_user_rox >= 0",
    )
    op.create_check_constraint(
        "ck_partner_promo_topup_user_min_nonnegative",
        "partner_promo_program_config",
        "topup_user_min_rub >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_partner_promo_topup_user_min_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_partner_promo_topup_user_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_column("partner_promo_program_config", "topup_user_min_rub")
    op.drop_column("partner_promo_program_config", "topup_user_rox")
