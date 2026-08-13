"""add product feed domain

Revision ID: 0014_feed_domain
Revises: 0013_generation_moderation
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_feed_domain"
down_revision: str | None = "0013_generation_moderation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column("publication_scope", sa.String(length=16), server_default="private", nullable=False),
    )
    op.add_column(
        "generations",
        sa.Column("is_public_feed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "generations",
        sa.Column("is_profile_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "generations",
        sa.Column("feed_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generations",
        sa.Column("shares_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "generations",
        sa.Column("feed_prompt_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "generations",
        sa.Column("feed_references_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("generations", sa.Column("source_feed_gen_id", sa.Uuid(), nullable=True))
    op.add_column("generations", sa.Column("parent_generation_id", sa.Uuid(), nullable=True))
    op.add_column("generations", sa.Column("action_type", sa.String(length=32), nullable=True))
    op.add_column(
        "generations",
        sa.Column("is_adult_content", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_check_constraint(
        "ck_generations_publication_scope",
        "generations",
        "publication_scope IN ('private', 'profile', 'feed')",
    )
    op.create_foreign_key(
        "fk_generations_source_feed_gen_id",
        "generations",
        "generations",
        ["source_feed_gen_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_generations_parent_generation_id",
        "generations",
        "generations",
        ["parent_generation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_generations_feed_recent",
        "generations",
        ["is_public_feed", "feed_published_at"],
    )
    op.create_index(
        "ix_generations_profile_recent",
        "generations",
        ["user_id", "is_profile_visible", "feed_published_at"],
    )
    op.create_index("ix_generations_source_feed", "generations", ["source_feed_gen_id"])
    op.create_index("ix_generations_parent_generation_id", "generations", ["parent_generation_id"])

    op.create_table(
        "feed_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("surface", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("surface IN ('feed', 'profile')", name="ck_feed_comments_surface"),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feed_comments_generation_id", "feed_comments", ["generation_id"])
    op.create_index("ix_feed_comments_user_id", "feed_comments", ["user_id"])
    op.create_index(
        "ix_feed_comments_generation_surface_created",
        "feed_comments",
        ["generation_id", "surface", "created_at"],
    )

    op.create_table(
        "feed_remix_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_generation_id", sa.Uuid(), nullable=False),
        sa.Column("remix_generation_id", sa.Uuid(), nullable=False),
        sa.Column("source_author_id", sa.Uuid(), nullable=False),
        sa.Column("remix_author_id", sa.Uuid(), nullable=False),
        sa.Column("credits_spent", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_generation_id"], ["generations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["remix_generation_id"], ["generations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["remix_author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_generation_id",
            "remix_generation_id",
            name="uq_feed_remix_source_result",
        ),
        sa.UniqueConstraint("remix_generation_id"),
    )
    op.create_index(
        "ix_feed_remix_source_created",
        "feed_remix_events",
        ["source_generation_id", "created_at"],
    )
    op.create_index(
        "ix_feed_remix_author_created",
        "feed_remix_events",
        ["remix_author_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feed_remix_author_created", table_name="feed_remix_events")
    op.drop_index("ix_feed_remix_source_created", table_name="feed_remix_events")
    op.drop_table("feed_remix_events")

    op.drop_index("ix_feed_comments_generation_surface_created", table_name="feed_comments")
    op.drop_index("ix_feed_comments_user_id", table_name="feed_comments")
    op.drop_index("ix_feed_comments_generation_id", table_name="feed_comments")
    op.drop_table("feed_comments")

    op.drop_index("ix_generations_parent_generation_id", table_name="generations")
    op.drop_index("ix_generations_source_feed", table_name="generations")
    op.drop_index("ix_generations_profile_recent", table_name="generations")
    op.drop_index("ix_generations_feed_recent", table_name="generations")
    op.drop_constraint("fk_generations_parent_generation_id", "generations", type_="foreignkey")
    op.drop_constraint("fk_generations_source_feed_gen_id", "generations", type_="foreignkey")
    op.drop_constraint("ck_generations_publication_scope", "generations", type_="check")

    for column in (
        "is_adult_content",
        "action_type",
        "parent_generation_id",
        "source_feed_gen_id",
        "feed_references_visible",
        "feed_prompt_visible",
        "shares_count",
        "feed_published_at",
        "is_profile_visible",
        "is_public_feed",
        "publication_scope",
    ):
        op.drop_column("generations", column)
