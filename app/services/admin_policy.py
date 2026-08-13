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


ACTION_POLICIES: dict[str, AdminActionPolicy] = {
    "users.block": AdminActionPolicy("users.manage", confirmation_required=True),
    "users.unblock": AdminActionPolicy("users.manage", confirmation_required=True),
    "users.balance_adjust": AdminActionPolicy(
        "users.wallet.adjust", confirmation_required=True, step_up_required=True
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
    "cms.save": AdminActionPolicy("cms.manage"),
    "cms.publish": AdminActionPolicy("cms.manage", confirmation_required=True),
    "campaigns.create": AdminActionPolicy("notifications.manage"),
    "campaigns.test": AdminActionPolicy("notifications.manage", confirmation_required=True),
    "campaigns.start": AdminActionPolicy(
        "notifications.manage", confirmation_required=True, step_up_required=True
    ),
    "campaigns.cancel": AdminActionPolicy("notifications.manage", confirmation_required=True),
    "prompts.moderate": AdminActionPolicy("prompts.manage", confirmation_required=True),
}


class AdminPolicy:
    @staticmethod
    def action(action: str) -> AdminActionPolicy:
        policy = ACTION_POLICIES.get(action)
        if policy is None:
            raise AdminPolicyError(f"Unknown admin action: {action}")
        return policy

    @staticmethod
    def require_permission(account: AdminAccount, permission: str) -> None:
        if not account.is_active or not has_permission(account, permission):
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
