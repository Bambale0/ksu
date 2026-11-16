"""Privacy-safe receipt and manual review of card refund/chargeback events."""

import sqlalchemy as sa
from alembic import op

revision = "0047_card_webhook_event_reviews"
down_revision = "0046_payment_reconcile_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_webhook_event_reviews",
        sa.Column("event_id_hash", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="manual_review"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_card_webhook_event_reviews_status_seen",
        "card_webhook_event_reviews",
        ["status", "first_seen_at"],
    )


def downgrade() -> None:
    # Do not destroy received evidence when rolling back application code.
    if op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM card_webhook_event_reviews)")
    ).scalar():
        raise RuntimeError("Cannot discard recorded card webhook review evidence")
    op.drop_index(
        "ix_card_webhook_event_reviews_status_seen",
        table_name="card_webhook_event_reviews",
    )
    op.drop_table("card_webhook_event_reviews")
