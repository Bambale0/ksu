"""partner application consent fields"""

import sqlalchemy as sa
from alembic import op

revision = "0024_partner_application_terms"
down_revision = "0023_partner_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("partner_applications", sa.Column("terms_version", sa.String(64), nullable=False, server_default="1"))
    op.add_column("partner_applications", sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("partner_applications", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("partner_applications", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("partner_applications", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    for name in ("updated_at", "created_at", "submitted_at", "agreed_at", "terms_version"):
        op.drop_column("partner_applications", name)
