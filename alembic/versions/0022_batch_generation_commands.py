"""idempotent batch generation commands"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_batch_generation_commands"
down_revision = "0021_batch_generation_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "batch_generation_commands",
        sa.Column("id", u, primary_key=True),
        sa.Column("batch_id", u, sa.ForeignKey("batch_generation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_generation_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('retry_failed')", name="ck_batch_generation_commands_kind"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_batch_generation_commands_user_idempotency"),
    )
    op.create_index("ix_batch_generation_commands_batch_id", "batch_generation_commands", ["batch_id"])
    op.create_index("ix_batch_generation_commands_user_id", "batch_generation_commands", ["user_id"])
    op.create_index("ix_batch_generation_commands_batch_created", "batch_generation_commands", ["batch_id", "created_at"])


def downgrade() -> None:
    op.drop_table("batch_generation_commands")
