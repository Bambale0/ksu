from __future__ import annotations

from app.db.models import AdminAccount
from app.services.admin_permissions import (
    ACTION_POLICIES as ACTION_POLICIES,
    ROLE_PERMISSION_SUPPLEMENTS as ROLE_PERMISSION_SUPPLEMENTS,
    AdminActionPolicy as AdminActionPolicy,
    has_effective_permission,
)


class AdminPolicyError(PermissionError):
    pass


class AdminPolicy:
    @staticmethod
    def action(action: str) -> AdminActionPolicy:
        policy = ACTION_POLICIES.get(action)
        if policy is None:
            raise AdminPolicyError(f"Unknown admin action: {action}")
        return policy

    @staticmethod
    def has_permission(account: AdminAccount, permission: str) -> bool:
        return has_effective_permission(account, permission)

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
