"""harden generation identity and publication invariants

Revision ID: 0035_generation_integrity
Revises: 0034_notification_gen_link
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_generation_integrity"
down_revision: str | None = "0034_notification_gen_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # publication_scope is canonical. Repair legacy compatibility flags before
    # enforcing the invariant so old rows cannot block a safe deployment.
    op.execute(
        """
        UPDATE generations
        SET
            is_public_feed = (publication_scope = 'feed'),
            is_profile_visible = (publication_scope IN ('profile', 'feed'))
        WHERE
            is_public_feed IS DISTINCT FROM (publication_scope = 'feed')
            OR is_profile_visible IS DISTINCT FROM (publication_scope IN ('profile', 'feed'))
        """
    )

    duplicate_groups = int(
        op.get_bind().scalar(
            sa.text(
                """
                SELECT count(*)
                FROM (
                    SELECT provider, external_id
                    FROM generations
                    WHERE provider IS NOT NULL
                      AND external_id IS NOT NULL
                    GROUP BY provider, external_id
                    HAVING count(*) > 1
                ) AS duplicates
                """
            )
        )
        or 0
    )
    if duplicate_groups:
        raise RuntimeError(
            "Cannot enforce generation provider identity: "
            f"{duplicate_groups} duplicate provider/external_id group(s) exist"
        )

    op.create_check_constraint(
        "ck_generations_publication_state",
        "generations",
        """
        (publication_scope = 'private' AND is_public_feed = false AND is_profile_visible = false)
        OR (publication_scope = 'profile' AND is_public_feed = false AND is_profile_visible = true)
        OR (publication_scope = 'feed' AND is_public_feed = true AND is_profile_visible = true)
        """,
    )
    op.create_index(
        "uq_generations_provider_external",
        "generations",
        ["provider", "external_id"],
        unique=True,
        postgresql_where=sa.text("provider IS NOT NULL AND external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_generations_provider_external", table_name="generations")
    op.drop_constraint(
        "ck_generations_publication_state",
        "generations",
        type_="check",
    )
