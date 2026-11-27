"""Product-owned preset images for named trend references."""

import sqlalchemy as sa
from alembic import op

revision = "0048_template_image"
down_revision = "0047_card_webhook_event_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_image_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False, unique=True),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('ready', 'deleted')", name="ck_template_image_status"),
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM template_image_references)"))
        .scalar()
    ):
        raise RuntimeError(
            "Keep preset images while trends or historical generations can reference them"
        )
    op.drop_table("template_image_references")
