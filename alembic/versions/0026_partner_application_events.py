"""partner application event log"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_partner_application_events"
down_revision = "0025_partner_application_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "partner_application_events",
        sa.Column("id", u, primary_key=True),
        sa.Column("application_id", u, sa.ForeignKey("partner_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", u, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_user_id", u, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_admin_id", u, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("actor_type IN ('user','admin','system')", name="ck_partner_application_events_actor_type"),
    )
    op.create_index("ix_partner_application_events_application_id", "partner_application_events", ["application_id"])
    op.create_index("ix_partner_application_events_user_id", "partner_application_events", ["user_id"])
    op.create_index("ix_partner_application_events_application_created", "partner_application_events", ["application_id", "created_at"])


def downgrade() -> None:
    op.drop_table("partner_application_events")
