"""partner application decision fields"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_partner_application_decision"
down_revision = "0024_partner_application_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.add_column("partner_applications", sa.Column("decided_at", sa.DateTime(timezone=True)))
    op.add_column("partner_applications", sa.Column("decided_by_admin_id", u, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")))
    op.add_column("partner_applications", sa.Column("decision_reason", sa.Text()))
    op.add_column("partner_applications", sa.Column("application_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.create_check_constraint("ck_partner_applications_status", "partner_applications", "status IN ('pending','approved','rejected','suspended')")
    op.create_index("ix_partner_applications_decided_by_admin_id", "partner_applications", ["decided_by_admin_id"])
    op.create_index("ix_partner_applications_status_updated", "partner_applications", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_partner_applications_status_updated", table_name="partner_applications")
    op.drop_index("ix_partner_applications_decided_by_admin_id", table_name="partner_applications")
    op.drop_constraint("ck_partner_applications_status", "partner_applications", type_="check")
    for name in ("application_data", "decision_reason", "decided_by_admin_id", "decided_at"):
        op.drop_column("partner_applications", name)
