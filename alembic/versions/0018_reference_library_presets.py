"""reference library and presets"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_reference_library_presets"
down_revision = "0017_prompt_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "user_references",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("label", sa.String(120)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("content_type", sa.String(255)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('image','video','audio')", name="ck_user_references_kind"),
        sa.CheckConstraint("status IN ('ready','deleted')", name="ck_user_references_status"),
        sa.UniqueConstraint("user_id", "source_url", name="uq_user_references_user_source"),
    )
    op.create_index("ix_user_references_user_id", "user_references", ["user_id"])
    op.create_index("ix_user_references_user_kind_created", "user_references", ["user_id", "kind", "created_at"])
    op.create_table(
        "user_presets",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("reference_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_user_presets_user_name"),
    )
    op.create_index("ix_user_presets_user_id", "user_presets", ["user_id"])
    op.create_index("ix_user_presets_user_updated", "user_presets", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_table("user_presets")
    op.drop_table("user_references")
