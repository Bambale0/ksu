"""add generation likes and user subscriptions

Revision ID: 0008_history_social
Revises: 0007_user_preferences
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_history_social"
down_revision: str | None = "0007_user_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_likes",
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("generation_id", "user_id"),
    )
    op.create_index(
        "ix_generation_likes_user_created",
        "generation_likes",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "user_subscriptions",
        sa.Column("subscriber_user_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subscriber_user_id <> author_user_id",
            name="ck_user_subscription_not_self",
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscriber_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("subscriber_user_id", "author_user_id"),
    )
    op.create_index(
        "ix_user_subscriptions_author_created",
        "user_subscriptions",
        ["author_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_subscriptions_subscriber_created",
        "user_subscriptions",
        ["subscriber_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_subscriptions_subscriber_created", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_author_created", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
    op.drop_index("ix_generation_likes_user_created", table_name="generation_likes")
    op.drop_table("generation_likes")
