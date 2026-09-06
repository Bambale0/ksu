"""link notifications to generations without reusing primary keys

Revision ID: 0034_notification_gen_link
Revises: 0033_partner_withdrawal_req
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_notification_gen_link"
down_revision: str | None = "0033_partner_withdrawal_req"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("generation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_notifications_generation_id_generations",
        "notifications",
        "generations",
        ["generation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_notifications_generation_id",
        "notifications",
        ["generation_id"],
    )
    # Preserve rich-generation delivery for legacy rows. Before this migration,
    # generation notifications used the generation UUID as their notification PK.
    op.execute(
        """
        UPDATE notifications AS n
        SET generation_id = g.id
        FROM generations AS g
        WHERE n.generation_id IS NULL
          AND n.id = g.id
          AND n.kind IN ('generation_succeeded', 'generation_failed')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_generation_id", table_name="notifications")
    op.drop_constraint(
        "fk_notifications_generation_id_generations",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "generation_id")
