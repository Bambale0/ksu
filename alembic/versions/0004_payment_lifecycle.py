"""payment lifecycle idempotency and reversals

Revision ID: 0004_payment_lifecycle
Revises: 0003_generation_outbox
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_payment_lifecycle"
down_revision: str | None = "0003_generation_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "payment_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "payment_id",
            UUID,
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("package_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="creating"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "request_key", name="uq_payment_request_user_key"),
    )
    op.create_index("ix_payment_requests_user_id", "payment_requests", ["user_id"])
    op.create_index(
        "ix_payment_requests_status_created",
        "payment_requests",
        ["status", "created_at"],
    )

    op.create_table(
        "payment_refund_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "payment_id",
            UUID,
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_refund_id", sa.String(128)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="creating"),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("payment_id", "request_key", name="uq_payment_refund_request_key"),
    )
    op.create_index("ix_payment_refund_requests_payment_id", "payment_refund_requests", ["payment_id"])
    op.create_index(
        "ix_payment_refund_requests_provider_refund_id",
        "payment_refund_requests",
        ["provider_refund_id"],
    )
    op.create_index(
        "ix_payment_refund_requests_status_created",
        "payment_refund_requests",
        ["status", "created_at"],
    )

    op.create_table(
        "payment_reversals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "payment_id",
            UUID,
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_event_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(192), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("credits", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_reversal_idempotency"),
    )
    op.create_index("ix_payment_reversals_payment_id", "payment_reversals", ["payment_id"])
    op.create_index(
        "ix_payment_reversals_payment_created",
        "payment_reversals",
        ["payment_id", "created_at"],
    )

    op.create_table(
        "referral_reward_reversals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "reward_id",
            UUID,
            sa.ForeignKey("referral_rewards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_reversal_id",
            UUID,
            sa.ForeignKey("payment_reversals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("reward_id", "payment_reversal_id", name="uq_reward_payment_reversal"),
    )
    op.create_index("ix_referral_reward_reversals_reward_id", "referral_reward_reversals", ["reward_id"])
    op.create_index(
        "ix_reward_reversals_reward",
        "referral_reward_reversals",
        ["reward_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reward_reversals_reward", table_name="referral_reward_reversals")
    op.drop_index("ix_referral_reward_reversals_reward_id", table_name="referral_reward_reversals")
    op.drop_table("referral_reward_reversals")
    op.drop_index("ix_payment_reversals_payment_created", table_name="payment_reversals")
    op.drop_index("ix_payment_reversals_payment_id", table_name="payment_reversals")
    op.drop_table("payment_reversals")
    op.drop_index("ix_payment_refund_requests_status_created", table_name="payment_refund_requests")
    op.drop_index(
        "ix_payment_refund_requests_provider_refund_id",
        table_name="payment_refund_requests",
    )
    op.drop_index("ix_payment_refund_requests_payment_id", table_name="payment_refund_requests")
    op.drop_table("payment_refund_requests")
    op.drop_index("ix_payment_requests_status_created", table_name="payment_requests")
    op.drop_index("ix_payment_requests_user_id", table_name="payment_requests")
    op.drop_table("payment_requests")
