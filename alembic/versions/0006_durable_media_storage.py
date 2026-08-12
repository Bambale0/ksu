"""add durable product-owned media storage

Revision ID: 0006_durable_media_storage
Revises: 0005_generation_history_state
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_durable_media_storage"
down_revision: str | None = "0005_generation_history_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_id", "ordinal", name="uq_media_asset_generation_ordinal"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_media_assets_generation_id", "media_assets", ["generation_id"], unique=False)
    op.create_index("ix_media_assets_user_id", "media_assets", ["user_id"], unique=False)
    op.create_index(
        "ix_media_assets_user_created",
        "media_assets",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_media_assets_generation_status",
        "media_assets",
        ["generation_id", "status"],
        unique=False,
    )

    op.create_table(
        "media_ingest_jobs",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id"),
    )
    op.create_index(
        "ix_media_ingest_status_available",
        "media_ingest_jobs",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_media_ingest_lease",
        "media_ingest_jobs",
        ["status", "lease_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_media_ingest_lease", table_name="media_ingest_jobs")
    op.drop_index("ix_media_ingest_status_available", table_name="media_ingest_jobs")
    op.drop_table("media_ingest_jobs")
    op.drop_index("ix_media_assets_generation_status", table_name="media_assets")
    op.drop_index("ix_media_assets_user_created", table_name="media_assets")
    op.drop_index("ix_media_assets_user_id", table_name="media_assets")
    op.drop_index("ix_media_assets_generation_id", table_name="media_assets")
    op.drop_table("media_assets")
