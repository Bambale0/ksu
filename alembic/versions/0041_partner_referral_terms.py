"""add partner-specific referral terms

Revision ID: 0041_partner_referral_terms
Revises: 0040_nexus_admin_tasks
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_partner_referral_terms"
down_revision: str | None = "0040_nexus_admin_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS partner_referral_terms (
                user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                first_line_percent numeric(5, 2) NOT NULL,
                second_line_percent numeric(5, 2) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ck_partner_terms_first_line_percent_range
                    CHECK (first_line_percent >= 0 AND first_line_percent <= 100),
                CONSTRAINT ck_partner_terms_second_line_percent_range
                    CHECK (second_line_percent >= 0 AND second_line_percent <= 100)
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("partner_referral_terms")
