"""add preset billing duration"""

import sqlalchemy as sa
from alembic import op

revision = "0019_preset_billing_seconds"
down_revision = "0018_reference_library_presets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_presets", sa.Column("billing_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_presets", "billing_seconds")
