"""persist Telegram generation delivery state

Revision ID: 0028_generation_telegram_delivery
Revises: 0027_prompt_tool_video
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_generation_telegram_delivery"
down_revision: str | None = "0027_prompt_tool_video"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "telegram_notification_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_scheduled",
        ),
    )
    op.add_column(
        "generations",
        sa.Column("telegram_notification_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("telegram_message_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generations", "telegram_message_id")
    op.drop_column("generations", "telegram_notification_sent_at")
    op.drop_column("generations", "telegram_notification_status")
