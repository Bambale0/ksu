"""extend reusable reference memory

Revision ID: 0029_reference_memory
Revises: 0028_generation_tg_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_reference_memory"
down_revision: str | None = "0028_generation_tg_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_references",
        sa.Column("file_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_references",
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_index(
        "uq_user_references_user_kind_hash",
        "user_references",
        ["user_id", "kind", "file_hash"],
        unique=True,
    )
    op.create_index(
        "ix_user_references_user_kind_last_used",
        "user_references",
        ["user_id", "kind", "last_used_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_references_user_kind_last_used", table_name="user_references")
    op.drop_index("uq_user_references_user_kind_hash", table_name="user_references")
    op.drop_column("user_references", "source")
    op.drop_column("user_references", "file_hash")
