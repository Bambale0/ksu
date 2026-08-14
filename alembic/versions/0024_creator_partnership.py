"""creator partnership applications agreements and monthly grants"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_creator_partnership"
down_revision = "0023_roxy_one_ruble_denomination"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "creator_partnership_applications",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("channel_name", sa.String(160), nullable=False),
        sa.Column("channel_url", sa.String(2048), nullable=False),
        sa.Column("audience_size", sa.Integer(), nullable=False),
        sa.Column("average_views", sa.Integer()),
        sa.Column("cooperation_format", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("decided_by_admin_id", u, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")),
        sa.Column("decision_note", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("audience_size >= 1", name="ck_creator_partnership_app_audience"),
        sa.CheckConstraint("average_views IS NULL OR average_views >= 0", name="ck_creator_partnership_app_views"),
        sa.CheckConstraint("status IN ('pending','approved','rejected','canceled')", name="ck_creator_partnership_app_status"),
    )
    op.create_index("ix_creator_partnership_applications_user_id", "creator_partnership_applications", ["user_id"])
    op.create_index("ix_creator_partnership_applications_decided_by_admin_id", "creator_partnership_applications", ["decided_by_admin_id"])
    op.create_index("ix_creator_partnership_app_user_created", "creator_partnership_applications", ["user_id", "created_at"])
    op.create_index("ix_creator_partnership_app_status_created", "creator_partnership_applications", ["status", "created_at"])

    op.create_table(
        "creator_partnership_agreements",
        sa.Column("id", u, primary_key=True),
        sa.Column("application_id", u, sa.ForeignKey("creator_partnership_applications.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("terms_summary", sa.Text(), nullable=False),
        sa.Column("monthly_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date()),
        sa.Column("approved_by_admin_id", u, sa.ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','paused','ended')", name="ck_creator_partnership_agreement_status"),
        sa.CheckConstraint("monthly_rox > 0", name="ck_creator_partnership_agreement_monthly_rox"),
    )
    op.create_index("ix_creator_partnership_agreements_user_id", "creator_partnership_agreements", ["user_id"])
    op.create_index("ix_creator_partnership_agreement_status", "creator_partnership_agreements", ["status"])
    op.create_index("ix_creator_partnership_agreement_user_created", "creator_partnership_agreements", ["user_id", "created_at"])

    op.create_table(
        "creator_partnership_grants",
        sa.Column("id", u, primary_key=True),
        sa.Column("agreement_id", u, sa.ForeignKey("creator_partnership_agreements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("amount_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("wallet_transaction_id", u, sa.ForeignKey("wallet_transactions.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("granted_by_admin_id", u, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(24), nullable=False, server_default="scheduler"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_rox > 0", name="ck_creator_partnership_grant_amount"),
        sa.CheckConstraint("source IN ('scheduler','admin')", name="ck_creator_partnership_grant_source"),
        sa.UniqueConstraint("agreement_id", "period", name="uq_creator_partnership_grant_period"),
    )
    op.create_index("ix_creator_partnership_grants_agreement_id", "creator_partnership_grants", ["agreement_id"])
    op.create_index("ix_creator_partnership_grants_user_id", "creator_partnership_grants", ["user_id"])
    op.create_index("ix_creator_partnership_grant_user_created", "creator_partnership_grants", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("creator_partnership_grants")
    op.drop_table("creator_partnership_agreements")
    op.drop_table("creator_partnership_applications")
