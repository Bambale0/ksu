"""Durable admin-owned video references for Kling 4 curated trends."""

import sqlalchemy as sa
from alembic import op

revision = "0045_template_video"
down_revision = "0044_trend_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_video_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False, unique=True),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("content_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("probe_status", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ready', 'deleted')", name="ck_template_video_status"),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM template_video_references)")).scalar():
        raise RuntimeError("Keep template videos while trends or historical generations can reference them")
    op.drop_table("template_video_references")
