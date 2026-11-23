"""Add first-class web accounts and verified identities without synthetic Telegram IDs."""
from alembic import op
import sqlalchemy as sa

revision = "0048_web_identity"
down_revision = "0047_card_webhook_event_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_table(
        "web_identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(320), nullable=False),
        sa.Column("display_email", sa.String(320)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "subject", name="uq_web_identity_provider_subject"),
        sa.UniqueConstraint("provider", "user_id", name="uq_web_identity_provider_user"),
    )
    op.create_index("ix_web_identities_user_id", "web_identities", ["user_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM web_identities)")).scalar():
        raise RuntimeError("Cannot downgrade web identities containing verified account bindings")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE telegram_id IS NULL)")).scalar():
        raise RuntimeError("Cannot downgrade: web-only customer accounts would be lost")
    op.drop_index("ix_web_identities_user_id", table_name="web_identities")
    op.drop_table("web_identities")
    op.alter_column("users", "telegram_id", existing_type=sa.BigInteger(), nullable=False)
