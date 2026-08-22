"""persist uploaded reference sizes

Revision ID: 0030_reference_size_bytes
Revises: 0029_reference_memory
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_reference_size_bytes"
down_revision: str | None = "0029_reference_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_references",
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_references", "size_bytes")
