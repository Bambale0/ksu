"""durable batch generation jobs"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_batch_generation"
down_revision = "0019_preset_billing_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "batch_generation_jobs",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("billing_seconds", sa.Integer()),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initial_cost_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_charged_rox", sa.Numeric(18, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('running','partial','succeeded','failed')", name="ck_batch_generation_jobs_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_batch_generation_jobs_user_idempotency"),
    )
    op.create_index("ix_batch_generation_jobs_user_id", "batch_generation_jobs", ["user_id"])
    op.create_index("ix_batch_generation_jobs_user_created", "batch_generation_jobs", ["user_id", "created_at"])
    op.create_index("ix_batch_generation_jobs_status_updated", "batch_generation_jobs", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_table("batch_generation_jobs")
