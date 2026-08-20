"""durable referral anti-fraud audit events"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_referral_antifraud"
down_revision = "0025_partner_wallet_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "referral_events",
        sa.Column("id", u, primary_key=True),
        sa.Column(
            "visitor_user_id",
            u,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("visitor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "inviter_user_id",
            u,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("inviter_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("attached", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_referral_events_inviter_created",
        "referral_events",
        ["inviter_user_id", "created_at"],
    )
    op.create_index(
        "ix_referral_events_visitor_created",
        "referral_events",
        ["visitor_user_id", "created_at"],
    )
    op.create_index(
        "ix_referral_events_reason_created",
        "referral_events",
        ["reason", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_events_reason_created", table_name="referral_events")
    op.drop_index("ix_referral_events_visitor_created", table_name="referral_events")
    op.drop_index("ix_referral_events_inviter_created", table_name="referral_events")
    op.drop_table("referral_events")
