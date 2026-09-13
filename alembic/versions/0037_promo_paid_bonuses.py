"""reserve promo bonuses for successful paid top-ups

Revision ID: 0037_promo_paid_bonuses
Revises: 0036_trend_collections
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_promo_paid_bonuses"
down_revision: str | None = "0036_trend_collections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promo_redemptions",
        sa.Column("payment_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "promo_redemptions",
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column(
        "promo_redemptions",
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "promo_redemptions",
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_promo_redemptions_payment_id_payments",
        "promo_redemptions",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_promo_payment",
        "promo_redemptions",
        ["payment_id"],
    )
    op.create_index(
        "ix_promo_redemptions_status_reserved",
        "promo_redemptions",
        ["promo_id", "status", "reserved_until"],
        unique=False,
    )
    op.execute(
        "UPDATE promo_redemptions "
        "SET status = 'applied', redeemed_at = created_at "
        "WHERE payment_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_promo_redemptions_status_reserved", table_name="promo_redemptions")
    op.drop_constraint("uq_promo_payment", "promo_redemptions", type_="unique")
    op.drop_constraint(
        "fk_promo_redemptions_payment_id_payments",
        "promo_redemptions",
        type_="foreignkey",
    )
    op.drop_column("promo_redemptions", "redeemed_at")
    op.drop_column("promo_redemptions", "reserved_until")
    op.drop_column("promo_redemptions", "status")
    op.drop_column("promo_redemptions", "payment_id")
