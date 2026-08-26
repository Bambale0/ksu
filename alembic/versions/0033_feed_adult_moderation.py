"""Allow user-submitted feed moderation requests before an admin decision.

Revision ID: 0033_feed_adult_moderation
Revises: 0032_generation_action_contexts
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_feed_adult_moderation"
down_revision = "0032_generation_action_contexts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "generation_moderation_state",
        "moderated_by_admin_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Pending rows are a 0033 concept. Remove them before restoring the old
    # invariant that every moderation state is attached to an admin decision.
    op.execute("DELETE FROM generation_moderation_state WHERE moderated_by_admin_id IS NULL")
    op.alter_column(
        "generation_moderation_state",
        "moderated_by_admin_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
