"""partner applications"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_partner_applications"
down_revision = "0022_batch_generation_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "partner_applications",
        sa.Column("id", u, primary_key=True),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.UniqueConstraint("user_id", name="uq_partner_applications_user"),
    )
    op.create_index("ix_partner_applications_user_id", "partner_applications", ["user_id"])


def downgrade() -> None:
    op.drop_table("partner_applications")
