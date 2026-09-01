"""durable partner withdrawal request idempotency

Revision ID: 0033_partner_withdrawal_req
Revises: 0032_generation_action_contexts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_partner_withdrawal_req"
down_revision: str | None = "0032_generation_action_contexts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "partner_withdrawal_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("withdrawal_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("amount_rub", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("requisites", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["withdrawal_id"], ["partner_withdrawals.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("withdrawal_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_partner_withdrawal_requests_user_idempotency",
        ),
    )
    op.create_index(
        "ix_partner_withdrawal_requests_user_id",
        "partner_withdrawal_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_partner_withdrawal_requests_user_created",
        "partner_withdrawal_requests",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_withdrawal_requests_user_created",
        table_name="partner_withdrawal_requests",
    )
    op.drop_index(
        "ix_partner_withdrawal_requests_user_id",
        table_name="partner_withdrawal_requests",
    )
    op.drop_table("partner_withdrawal_requests")
