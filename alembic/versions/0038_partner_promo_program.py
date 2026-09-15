"""partner promo program attribution and economics

Revision ID: 0038_partner_promo_program
Revises: 0037_promo_paid_bonuses
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_partner_promo_program"
down_revision: str | None = "0037_promo_paid_bonuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "partner_promo_program_config",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("welcome_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("first_line_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("topup_partner_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("welcome_rox >= 0", name="ck_partner_promo_welcome_nonnegative"),
        sa.CheckConstraint(
            "first_line_percent >= 0 AND first_line_percent <= 100",
            name="ck_partner_promo_percent_range",
        ),
        sa.CheckConstraint("topup_partner_rox >= 0", name="ck_partner_promo_topup_nonnegative"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(
        sa.text(
            "INSERT INTO partner_promo_program_config "
            "(key, welcome_rox, first_line_percent, topup_partner_rox, is_active) "
            "VALUES ('default', 25, 30, 10, true)"
        )
    )

    op.add_column("promo_codes", sa.Column("partner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_promo_codes_partner_user_id_users",
        "promo_codes",
        "users",
        ["partner_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_promo_codes_partner_user_id",
        "promo_codes",
        ["partner_user_id"],
        unique=False,
    )

    op.add_column(
        "referral_relations",
        sa.Column("source", sa.String(length=16), server_default="link", nullable=False),
    )
    op.add_column("referral_relations", sa.Column("promo_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_referral_relation_source",
        "referral_relations",
        "source IN ('link', 'promo')",
    )
    op.create_foreign_key(
        "fk_referral_relations_promo_id_promo_codes",
        "referral_relations",
        "promo_codes",
        ["promo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_referral_relations_inviter_source",
        "referral_relations",
        ["inviter_user_id", "source"],
        unique=False,
    )
    op.create_index(
        "ix_referral_relations_promo_id",
        "referral_relations",
        ["promo_id"],
        unique=False,
    )

    op.add_column("wallet_transactions", sa.Column("reason", sa.String(length=64), nullable=True))
    op.add_column("wallet_transactions", sa.Column("promo_code", sa.String(length=64), nullable=True))
    op.add_column("wallet_transactions", sa.Column("partner_id", sa.Uuid(), nullable=True))
    op.add_column("wallet_transactions", sa.Column("referral_user_id", sa.Uuid(), nullable=True))
    op.add_column("wallet_transactions", sa.Column("payment_id", sa.Uuid(), nullable=True))

    op.add_column("referral_rewards", sa.Column("reason", sa.String(length=64), nullable=True))
    op.add_column("referral_rewards", sa.Column("promo_id", sa.Uuid(), nullable=True))
    op.add_column("referral_rewards", sa.Column("promo_code", sa.String(length=64), nullable=True))
    op.add_column("referral_rewards", sa.Column("payment_id", sa.Uuid(), nullable=True))

def downgrade() -> None:
    op.drop_column("referral_rewards", "payment_id")
    op.drop_column("referral_rewards", "promo_code")
    op.drop_column("referral_rewards", "promo_id")
    op.drop_column("referral_rewards", "reason")

    op.drop_column("wallet_transactions", "payment_id")
    op.drop_column("wallet_transactions", "referral_user_id")
    op.drop_column("wallet_transactions", "partner_id")
    op.drop_column("wallet_transactions", "promo_code")
    op.drop_column("wallet_transactions", "reason")

    op.drop_index("ix_referral_relations_promo_id", table_name="referral_relations")
    op.drop_index("ix_referral_relations_inviter_source", table_name="referral_relations")
    op.drop_constraint("ck_referral_relation_source", "referral_relations", type_="check")
    op.drop_constraint(
        "fk_referral_relations_promo_id_promo_codes",
        "referral_relations",
        type_="foreignkey",
    )
    op.drop_column("referral_relations", "promo_id")
    op.drop_column("referral_relations", "source")

    op.drop_index("ix_promo_codes_partner_user_id", table_name="promo_codes")
    op.drop_constraint(
        "fk_promo_codes_partner_user_id_users",
        "promo_codes",
        type_="foreignkey",
    )
    op.drop_column("promo_codes", "partner_user_id")

    op.drop_table("partner_promo_program_config")
