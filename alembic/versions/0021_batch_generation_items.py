"""durable batch generation items"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_batch_generation_items"
down_revision = "0020_batch_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "batch_generation_items",
        sa.Column("id", u, primary_key=True),
        sa.Column("batch_id", u, sa.ForeignKey("batch_generation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("input_url", sa.Text(), nullable=False),
        sa.Column("generation_id", u, sa.ForeignKey("generations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_batch_generation_items_ordinal"),
        sa.UniqueConstraint("generation_id", name="uq_batch_generation_items_generation"),
    )
    op.create_index("ix_batch_generation_items_batch_id", "batch_generation_items", ["batch_id"])
    op.create_index("ix_batch_generation_items_generation_id", "batch_generation_items", ["generation_id"])
    op.create_index("ix_batch_generation_items_batch_ordinal", "batch_generation_items", ["batch_id", "ordinal"])


def downgrade() -> None:
    op.drop_table("batch_generation_items")
