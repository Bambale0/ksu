"""harden admin privilege revocation trigger

Revision ID: 0015_harden_admin_revoke
Revises: 0014_revoke_admin_user
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_harden_admin_revoke"
down_revision: str | None = "0014_revoke_admin_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ksu_revoke_admin_on_user_deactivation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.is_active = FALSE AND OLD.is_active IS DISTINCT FROM NEW.is_active THEN
                UPDATE admin_accounts
                SET is_active = FALSE,
                    updated_at = now()
                WHERE user_id = NEW.id
                  AND is_active = TRUE;

                UPDATE admin_sessions
                SET revoked_at = COALESCE(revoked_at, now()),
                    revoke_reason = COALESCE(revoke_reason, 'linked_user_deactivated')
                WHERE admin_id IN (
                    SELECT id FROM admin_accounts WHERE user_id = NEW.id
                )
                  AND revoked_at IS NULL;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
    # The 0014 definition is equivalent except for a non-essential timestamp update.
    # Keep the safe function body during downgrade to 0014; 0014 downgrade removes it.
    pass
