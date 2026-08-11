"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid()
MONEY = sa.Numeric(18, 2)
TS = sa.DateTime(timezone=True)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(255)),
        sa.Column("language_code", sa.String(16)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "wallets",
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance", MONEY, nullable=False, server_default="0"),
        *timestamps(),
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("balance_before", MONEY, nullable=False),
        sa.Column("balance_after", MONEY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("reference_type", sa.String(64)),
        sa.Column("reference_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"])
    op.create_index(
        "ix_wallet_transactions_user_created", "wallet_transactions", ["user_id", "created_at"]
    )

    op.create_table(
        "promo_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("reward_amount", MONEY, nullable=False),
        sa.Column("max_uses", sa.Integer()),
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", TS),
        *timestamps(),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)

    op.create_table(
        "promo_redemptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("promo_id", UUID, sa.ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("promo_id", "user_id", name="uq_promo_user"),
    )

    op.create_table(
        "referral_relations",
        sa.Column(
            "referred_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("inviter_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_referral_relations_inviter_user_id", "referral_relations", ["inviter_user_id"])

    op.create_table(
        "generations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("input_url", sa.Text()),
        sa.Column("result_url", sa.Text()),
        sa.Column("cost_rox", MONEY, nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("external_id", sa.String(128)),
        sa.Column("error", sa.Text()),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
    )
    op.create_index("ix_generations_user_id", "generations", ["user_id"])
    op.create_index("ix_generations_external_id", "generations", ["external_id"])
    op.create_index("ix_generations_user_created", "generations", ["user_id", "created_at"])

    op.create_table(
        "payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(128), unique=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("rox_amount", MONEY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])

    op.create_table(
        "partner_withdrawals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("requisites", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
    )
    op.create_index("ix_partner_withdrawals_user_id", "partner_withdrawals", ["user_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        *timestamps(),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])

    op.create_table(
        "support_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticket_id", UUID, sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "referral_rewards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("partner_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_transaction_id",
            UUID,
            sa.ForeignKey("wallet_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("partner_user_id", "source_transaction_id", "level", name="uq_ref_reward"),
    )
    op.create_index("ix_referral_rewards_partner_user_id", "referral_rewards", ["partner_user_id"])


def downgrade() -> None:
    for table in [
        "referral_rewards",
        "notifications",
        "support_messages",
        "support_tickets",
        "partner_withdrawals",
        "payments",
        "generations",
        "referral_relations",
        "promo_redemptions",
        "promo_codes",
        "wallet_transactions",
        "wallets",
        "users",
    ]:
        op.drop_table(table)
