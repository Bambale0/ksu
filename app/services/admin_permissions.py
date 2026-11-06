from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models import AdminAccount


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.pii",
            "users.manage",
            "users.wallet.adjust",
            "users.notes",
            "generations.read",
            "generations.manage",
            "payments.read",
            "promocodes.read",
            "promocodes.manage",
            "support.read",
            "support.manage",
            "withdrawals.read",
            "withdrawals.manage",
            "referrals.read",
            "audit.read",
            "admins.read",
            "security.read",
            "sessions.manage",
        }
    ),
    "support": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.notes",
            "generations.read",
            "payments.read",
            "support.read",
            "support.manage",
        }
    ),
    "finance": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.pii",
            "users.wallet.adjust",
            "payments.read",
            "withdrawals.read",
            "withdrawals.manage",
            "referrals.read",
            "audit.read",
        }
    ),
    "moderator": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.manage",
            "users.notes",
            "generations.read",
            "generations.manage",
            "support.read",
        }
    ),
    "auditor": frozenset(
        {
            "dashboard.read",
            "users.read",
            "generations.read",
            "payments.read",
            "promocodes.read",
            "support.read",
            "withdrawals.read",
            "referrals.read",
            "audit.read",
            "admins.read",
            "security.read",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class AdminActionPolicy:
    permission: str
    confirmation_required: bool = False
    step_up_required: bool = False


ROLE_PERMISSION_SUPPLEMENTS: dict[str, frozenset[str]] = {
    "admin": frozenset(
        {
            "finance.read",
            "operations.read",
            "operations.manage",
            "payments.manage",
            "partners.read",
            "partners.manage",
            "pricing.read",
            "pricing.manage",
            "prompts.read",
            "prompts.manage",
            "cms.read",
            "cms.manage",
            "notifications.read",
            "notifications.manage",
            "social.moderate",
            "runtime.manage",
            "ai_admin.use",
        }
    ),
    "finance": frozenset(
        {
            "finance.read",
            "payments.manage",
            "partners.read",
            "partners.manage",
            "pricing.read",
            "pricing.manage",
            "operations.read",
            "operations.manage",
        }
    ),
    "support": frozenset({"operations.read"}),
    "moderator": frozenset(
        {
            "operations.read",
            "prompts.read",
            "prompts.manage",
            "social.moderate",
            "cms.read",
        }
    ),
    "auditor": frozenset(
        {
            "finance.read",
            "operations.read",
            "partners.read",
            "pricing.read",
            "prompts.read",
            "cms.read",
            "notifications.read",
        }
    ),
}


ACTION_POLICIES: dict[str, AdminActionPolicy] = {
    "users.block": AdminActionPolicy("users.manage", confirmation_required=True),
    "users.unblock": AdminActionPolicy("users.manage", confirmation_required=True),
    "users.balance_adjust": AdminActionPolicy(
        "users.wallet.adjust", confirmation_required=True, step_up_required=True
    ),
    "partners.withdrawal_manage": AdminActionPolicy(
        "partners.manage", confirmation_required=True, step_up_required=True
    ),
    "creator_partnership.decide": AdminActionPolicy(
        "partners.manage", confirmation_required=True
    ),
    "creator_partnership.update": AdminActionPolicy(
        "partners.manage", confirmation_required=True
    ),
    "creator_partnership.grant": AdminActionPolicy(
        "partners.manage", confirmation_required=True, step_up_required=True
    ),
    "payments.recheck": AdminActionPolicy("payments.read"),
    "payments.reprocess": AdminActionPolicy(
        "payments.manage", confirmation_required=True, step_up_required=True
    ),
    "operations.replay": AdminActionPolicy(
        "operations.manage", confirmation_required=True, step_up_required=True
    ),
    "operations.refund": AdminActionPolicy(
        "operations.manage", confirmation_required=True, step_up_required=True
    ),
    "support.assign": AdminActionPolicy("support.manage"),
    "support.update": AdminActionPolicy("support.manage"),
    "support.reply": AdminActionPolicy("support.manage", confirmation_required=True),
    "tariffs.publish": AdminActionPolicy(
        "pricing.manage", confirmation_required=True, step_up_required=True
    ),
    "promos.manage": AdminActionPolicy("promocodes.manage", confirmation_required=True),
    "cms.save": AdminActionPolicy("cms.manage"),
    "cms.publish": AdminActionPolicy("cms.manage", confirmation_required=True),
    "campaigns.create": AdminActionPolicy("notifications.manage"),
    "campaigns.test": AdminActionPolicy("notifications.manage", confirmation_required=True),
    "campaigns.start": AdminActionPolicy(
        "notifications.manage", confirmation_required=True, step_up_required=True
    ),
    "campaigns.cancel": AdminActionPolicy("notifications.manage", confirmation_required=True),
    "prompts.moderate": AdminActionPolicy("prompts.manage", confirmation_required=True),
    "social.moderate": AdminActionPolicy("social.moderate", confirmation_required=True),
    "runtime.reload": AdminActionPolicy("runtime.manage", confirmation_required=True),
    "runtime.prompt_tool_routes": AdminActionPolicy(
        "runtime.manage", confirmation_required=True, step_up_required=True
    ),
    "runtime.neironych_balance_alert": AdminActionPolicy(
        "runtime.manage", confirmation_required=True, step_up_required=True
    ),
}


def has_permission(admin: AdminAccount, permission: str) -> bool:
    base = ROLE_PERMISSIONS.get(admin.role, frozenset())
    overrides = admin.permission_overrides or {}
    deny = {str(item) for item in overrides.get("deny", [])}
    allow = {str(item) for item in overrides.get("allow", [])}
    if permission in deny or "*" in deny:
        return False
    if "*" in base or permission in base:
        return True
    return permission in allow or "*" in allow


def has_effective_permission(account: AdminAccount, permission: str) -> bool:
    if not account.is_active:
        return False
    if has_permission(account, permission):
        return True
    overrides = account.permission_overrides or {}
    denied = frozenset(str(value) for value in overrides.get("deny", []))
    if permission in denied or "*" in denied:
        return False
    granted = frozenset(str(value) for value in overrides.get("allow", []))
    if permission in granted or "*" in granted:
        return True
    return permission in ROLE_PERMISSION_SUPPLEMENTS.get(account.role, frozenset())


# The catalog is used only to enumerate UI capabilities when a wildcard has
# explicit exceptions. Runtime authorization remains an open-ended predicate.
KNOWN_ADMIN_PERMISSIONS: frozenset[str] = frozenset().union(
    *ROLE_PERMISSIONS.values(),
    *ROLE_PERMISSION_SUPPLEMENTS.values(),
    (policy.permission for policy in ACTION_POLICIES.values()),
    {"admins.manage"},  # Owner-only account management is not a delegated role grant.
) - {"*"}


def effective_permissions(admin: AdminAccount) -> list[str]:
    """Describe the effective endpoint policy without hiding explicit denies."""
    if not admin.is_active:
        return []
    overrides = admin.permission_overrides or {}
    deny = {str(item) for item in overrides.get("deny", [])}
    allow = {str(item) for item in overrides.get("allow", [])}
    if "*" in deny:
        return []
    base = ROLE_PERMISSIONS.get(admin.role, frozenset())
    wildcard = "*" in base or "*" in allow
    if wildcard and not deny:
        return ["*"]
    candidates = (
        KNOWN_ADMIN_PERMISSIONS
        if wildcard
        else base | ROLE_PERMISSION_SUPPLEMENTS.get(admin.role, frozenset())
    )
    return sorted(
        permission
        for permission in (candidates | allow) - {"*"}
        if has_effective_permission(admin, permission)
    )
