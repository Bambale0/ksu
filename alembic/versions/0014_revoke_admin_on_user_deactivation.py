"""revoke admin privileges when the linked user is deactivated

Revision ID: 0014_revoke_admin_user
Revises: 0013_generation_moderation
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_revoke_admin_user"
down_revision: str | None = "0013_generation_moderation"
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
                    revoke_reason = COALESCE(revoke_reason, 'linked_user_deactivated'),
                    updated_at = now()
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
    op.execute(
        """
        CREATE TRIGGER trg_ksu_revoke_admin_on_user_deactivation
        AFTER UPDATE OF is_active ON users
        FOR EACH ROW
        EXECUTE FUNCTION ksu_revoke_admin_on_user_deactivation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ksu_revoke_admin_on_user_deactivation ON users;"
    )
    op.execute("DROP FUNCTION IF EXISTS ksu_revoke_admin_on_user_deactivation();")
