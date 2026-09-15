"""package bonuses and promo top-up reward

Revision ID: 0039_package_promo_topup
Revises: 0038_partner_promo_program
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_package_promo_topup"
down_revision: str | None = "0038_partner_promo_program"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partner_promo_program_config",
        sa.Column(
            "payment_bonus_rox",
            sa.Numeric(18, 2),
            server_default=sa.text("50"),
            nullable=False,
        ),
    )
    op.add_column(
        "partner_promo_program_config",
        sa.Column(
            "payment_bonus_min_rub",
            sa.Numeric(18, 2),
            server_default=sa.text("1000"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_partner_promo_payment_bonus_nonnegative",
        "partner_promo_program_config",
        "payment_bonus_rox >= 0",
    )
    op.create_check_constraint(
        "ck_partner_promo_payment_min_nonnegative",
        "partner_promo_program_config",
        "payment_bonus_min_rub >= 0",
    )
    op.execute(
        sa.text(
            "UPDATE partner_promo_program_config "
            "SET welcome_rox = 0, payment_bonus_rox = 50, payment_bonus_min_rub = 1000 "
            "WHERE key = 'default'"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_partner_promo_payment_min_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_partner_promo_payment_bonus_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_column("partner_promo_program_config", "payment_bonus_min_rub")
    op.drop_column("partner_promo_program_config", "payment_bonus_rox")
