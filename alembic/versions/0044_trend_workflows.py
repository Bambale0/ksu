"""Add durable owner-scoped trend photo/video workflow runs and steps."""

import sqlalchemy as sa
from alembic import op

revision = "0044_trend_workflows"
down_revision = "0043_template_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_workflow_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trend_id", sa.Uuid(), sa.ForeignKey("admin_trends.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recipe_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("recipe_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("usage_incremented", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "trend_id", "command_key", name="uq_trend_workflow_start_command"),
        sa.CheckConstraint(
            "status IN ('created', 'running', 'step1_ready', 'completed', 'failed')",
            name="ck_trend_workflow_run_status",
        ),
    )
    op.create_index("ix_trend_workflow_runs_user_created", "trend_workflow_runs", ["user_id", "created_at"])
    op.create_index("ix_trend_workflow_runs_trend_status", "trend_workflow_runs", ["trend_id", "status"])

    op.create_table(
        "trend_workflow_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("trend_workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("generation_id", sa.Uuid(), sa.ForeignKey("generations.id", ondelete="SET NULL")),
        sa.Column("media_asset_id", sa.Uuid(), sa.ForeignKey("media_assets.id", ondelete="SET NULL")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("command_key", sa.String(160)),
        sa.Column("payload_hash", sa.String(64)),
        sa.Column("last_error", sa.Text()),
        sa.Column("reserved_generation_id", sa.Uuid()),
        sa.Column("attempt_history", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workflow_id", "step_key", name="uq_trend_workflow_step_key"),
        sa.UniqueConstraint("workflow_id", "ordinal", name="uq_trend_workflow_step_ordinal"),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'ready', 'completed', 'failed')",
            name="ck_trend_workflow_step_status",
        ),
    )
    op.create_index("ix_trend_workflow_steps_generation", "trend_workflow_steps", ["generation_id"])
    op.create_index("ix_trend_workflow_steps_asset", "trend_workflow_steps", ["media_asset_id"])


def downgrade() -> None:
    bind = op.get_bind()
    has_rows = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM trend_workflow_runs) "
            "OR EXISTS (SELECT 1 FROM trend_workflow_steps)"
        )
    ).scalar()
    if has_rows:
        raise RuntimeError(
            "Refusing to downgrade while trend workflow state exists; "
            "perform an application rollback and preserve these tables."
        )
    op.drop_index("ix_trend_workflow_steps_asset", table_name="trend_workflow_steps")
    op.drop_index("ix_trend_workflow_steps_generation", table_name="trend_workflow_steps")
    op.drop_table("trend_workflow_steps")
    op.drop_index("ix_trend_workflow_runs_trend_status", table_name="trend_workflow_runs")
    op.drop_index("ix_trend_workflow_runs_user_created", table_name="trend_workflow_runs")
    op.drop_table("trend_workflow_runs")
