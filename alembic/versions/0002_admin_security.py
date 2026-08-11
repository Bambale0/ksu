"""admin security contour

Revision ID: 0002_admin_security
Revises: 0001_initial
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_admin_security"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="auditor"),
        sa.Column("permission_overrides", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mfa_secret_encrypted", sa.Text()),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_confirmed_at", TS),
        sa.Column("recovery_code_hashes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TS),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_login_at", TS),
        sa.Column("last_login_ip_hash", sa.String(64)),
        sa.Column("created_by_admin_id", UUID),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_foreign_key(
        "fk_admin_accounts_created_by",
        "admin_accounts",
        "admin_accounts",
        ["created_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_admin_accounts_user_id", "admin_accounts", ["user_id"], unique=True)
    op.create_index("ix_admin_accounts_role_active", "admin_accounts", ["role", "is_active"])

    op.create_table(
        "admin_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("admin_id", UUID, sa.ForeignKey("admin_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("idle_expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.Column("revoke_reason", sa.String(255)),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("step_up_until", TS),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])
    op.create_index(
        "ix_admin_sessions_admin_active",
        "admin_sessions",
        ["admin_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("admin_id", UUID, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")),
        sa.Column("session_id", UUID, sa.ForeignKey("admin_sessions.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("reason", sa.Text()),
        sa.Column("request_id", sa.String(64)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("integrity_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_audit_logs_admin_id", "admin_audit_logs", ["admin_id"])
    op.create_index("ix_admin_audit_created", "admin_audit_logs", ["created_at"])
    op.create_index("ix_admin_audit_action_created", "admin_audit_logs", ["action", "created_at"])
    op.create_index(
        "ix_admin_audit_resource",
        "admin_audit_logs",
        ["resource_type", "resource_id", "created_at"],
    )

    op.create_table(
        "admin_user_notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", UUID, sa.ForeignKey("admin_accounts.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_user_notes_user_id", "admin_user_notes", ["user_id"])
    op.create_index(
        "ix_admin_user_notes_user_created",
        "admin_user_notes",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("admin_user_notes")
    op.drop_table("admin_audit_logs")
    op.drop_table("admin_sessions")
    op.drop_constraint("fk_admin_accounts_created_by", "admin_accounts", type_="foreignkey")
    op.drop_table("admin_accounts")
