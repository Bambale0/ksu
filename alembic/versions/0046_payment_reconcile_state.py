"""Durable payment reconciliation retry schedule (expand-first)."""

import sqlalchemy as sa
from alembic import op

revision = "0046_payment_reconcile_state"
down_revision = "0045_template_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_reconcile_state",
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(64)),
    )
    op.create_index(
        "ix_payment_reconcile_state_next",
        "payment_reconcile_state",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    # Only local scheduling metadata is deleted; no payments or ledger entries.
    op.drop_index("ix_payment_reconcile_state_next", table_name="payment_reconcile_state")
    op.drop_table("payment_reconcile_state")