"""add prompt tool task schema

Revision ID: 0017_prompt_tools
Revises: 0016_feed_domain
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_prompt_tools"
down_revision: str | None = "0016_feed_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_tool_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="kie"),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("cost_credits", sa.Numeric(18, 2), nullable=False),
        sa.Column("provider_credits", sa.Numeric(18, 4), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "tool IN ('image_analysis', 'prompt_builder')",
            name="ck_prompt_tool_tasks_tool",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'succeeded', 'failed')",
            name="ck_prompt_tool_tasks_status",
        ),
    )
    op.create_index("ix_prompt_tool_tasks_user_id", "prompt_tool_tasks", ["user_id"])
    op.create_index(
        "ix_prompt_tool_tasks_user_created",
        "prompt_tool_tasks",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_prompt_tool_tasks_status_created",
        "prompt_tool_tasks",
        ["status", "created_at"],
    )

    op.create_table(
        "prompt_tool_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "prompt_tool_tasks.id",
                ondelete="CASCADE",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_prompt_tool_outbox_task"),
    )
    op.create_index(
        "ix_prompt_tool_outbox_claim",
        "prompt_tool_outbox",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_prompt_tool_outbox_lease",
        "prompt_tool_outbox",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_tool_outbox_lease", table_name="prompt_tool_outbox")
    op.drop_index("ix_prompt_tool_outbox_claim", table_name="prompt_tool_outbox")
    op.drop_table("prompt_tool_outbox")
    op.drop_index("ix_prompt_tool_tasks_status_created", table_name="prompt_tool_tasks")
    op.drop_index("ix_prompt_tool_tasks_user_created", table_name="prompt_tool_tasks")
    op.drop_index("ix_prompt_tool_tasks_user_id", table_name="prompt_tool_tasks")
    op.drop_table("prompt_tool_tasks")
