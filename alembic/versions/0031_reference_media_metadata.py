"""persist trusted reference media metadata

Revision ID: 0031_reference_media_metadata
Revises: 0030_reference_size_bytes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_reference_media_metadata"
down_revision: str | None = "0030_reference_size_bytes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_references", sa.Column("duration_ms", sa.BigInteger(), nullable=True))
    op.add_column("user_references", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("user_references", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("user_references", sa.Column("container", sa.String(length=64), nullable=True))
    op.add_column("user_references", sa.Column("video_codec", sa.String(length=64), nullable=True))
    op.add_column("user_references", sa.Column("audio_codec", sa.String(length=64), nullable=True))
    op.add_column("user_references", sa.Column("probe_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("user_references", "probe_status")
    op.drop_column("user_references", "audio_codec")
    op.drop_column("user_references", "video_codec")
    op.drop_column("user_references", "container")
    op.drop_column("user_references", "height")
    op.drop_column("user_references", "width")
    op.drop_column("user_references", "duration_ms")
