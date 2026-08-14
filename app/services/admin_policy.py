from __future__ import annotations

from dataclasses import dataclass

from app.db.models import AdminAccount
from app.services.admin_security import has_permission


class AdminPolicyError(PermissionError):
    pass


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
}


class AdminPolicy:
    @staticmethod
    def action(action: str) -> AdminActionPolicy:
        policy = ACTION_POLICIES.get(action)
        if policy is None:
            raise AdminPolicyError(f"Unknown admin action: {action}")
        return policy

    @staticmethod
    def has_permission(account: AdminAccount, permission: str) -> bool:
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

    @classmethod
    def require_permission(cls, account: AdminAccount, permission: str) -> None:
        if not cls.has_permission(account, permission):
            raise AdminPolicyError(f"Missing admin permission: {permission}")

    @classmethod
    def authorize_action(
        cls,
        account: AdminAccount,
        action: str,
        *,
        confirmed: bool = False,
        step_up_valid: bool = False,
    ) -> AdminActionPolicy:
        policy = cls.action(action)
        cls.require_permission(account, policy.permission)
        if policy.confirmation_required and not confirmed:
            raise AdminPolicyError("Explicit confirmation required")
        if policy.step_up_required and not step_up_valid:
            raise AdminPolicyError("Fresh MFA step-up required")
        return policy
