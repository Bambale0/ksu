"""partner earnings transfers to the ROX wallet"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_partner_wallet_transfers"
down_revision = "0024_creator_partnership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "partner_wallet_transfers",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column("rox_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "wallet_transaction_id",
            u,
            sa.ForeignKey("wallet_transactions.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("amount_rub > 0", name="ck_partner_wallet_transfer_amount"),
        sa.CheckConstraint("rox_amount > 0", name="ck_partner_wallet_transfer_rox"),
    )
    op.create_index(
        "ix_partner_wallet_transfers_user_id",
        "partner_wallet_transfers",
        ["user_id"],
    )
    op.create_index(
        "ix_partner_wallet_transfers_user_created",
        "partner_wallet_transfers",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_wallet_transfers_user_created",
        table_name="partner_wallet_transfers",
    )
    op.drop_index("ix_partner_wallet_transfers_user_id", table_name="partner_wallet_transfers")
    op.drop_table("partner_wallet_transfers")
