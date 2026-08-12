"""durable generation outbox

Revision ID: 0003_generation_outbox
Revises: 0002_admin_security
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_generation_outbox"
down_revision: str | None = "0002_admin_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "generation_outbox",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "generation_id",
            UUID,
            sa.ForeignKey("generations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", TS),
        sa.Column("completed_at", TS),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_generation_outbox_claim",
        "generation_outbox",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_generation_outbox_lease",
        "generation_outbox",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_generation_outbox_lease", table_name="generation_outbox")
    op.drop_index("ix_generation_outbox_claim", table_name="generation_outbox")
    op.drop_table("generation_outbox")
