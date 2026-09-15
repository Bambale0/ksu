"""move partner promo user reward to successful paid top-ups

Revision ID: 0039_partner_promo_paid_user_bonus
Revises: 0038_partner_promo_program
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_partner_promo_paid_user_bonus"
down_revision: str | None = "0038_partner_promo_program"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partner_promo_program_config",
        sa.Column("payment_bonus_rox", sa.Numeric(18, 2), nullable=False, server_default="50"),
    )
    op.add_column(
        "partner_promo_program_config",
        sa.Column("min_payment_rub", sa.Numeric(18, 2), nullable=False, server_default="1000"),
    )
    op.create_check_constraint(
        "ck_partner_promo_payment_bonus_nonnegative",
        "partner_promo_program_config",
        "payment_bonus_rox >= 0",
    )
    op.create_check_constraint(
        "ck_partner_promo_min_payment_nonnegative",
        "partner_promo_program_config",
        "min_payment_rub >= 0",
    )
    op.execute(
        "UPDATE partner_promo_program_config "
        "SET welcome_rox = 0, payment_bonus_rox = 50, min_payment_rub = 1000 "
        "WHERE key = 'default'"
    )
    op.alter_column("partner_promo_program_config", "payment_bonus_rox", server_default=None)
    op.alter_column("partner_promo_program_config", "min_payment_rub", server_default=None)


def downgrade() -> None:
    op.execute(
        "UPDATE partner_promo_program_config "
        "SET welcome_rox = 25 "
        "WHERE key = 'default' AND welcome_rox = 0"
    )
    op.drop_constraint(
        "ck_partner_promo_min_payment_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_partner_promo_payment_bonus_nonnegative",
        "partner_promo_program_config",
        type_="check",
    )
    op.drop_column("partner_promo_program_config", "min_payment_rub")
    op.drop_column("partner_promo_program_config", "payment_bonus_rox")
