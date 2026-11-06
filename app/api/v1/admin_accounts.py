from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import AdminAccount, AdminSession, User
from app.services.support_recipient_config import SupportRecipientConfigService
from app.services.admin_security import (
    AdminAuditService,
    ROLE_PERMISSIONS,
    VALID_ADMIN_ROLES,
    effective_permissions,
    utcnow,
)

router = APIRouter(prefix="/admin", tags=["admin-accounts"])

AdminsReadDep = Annotated[AdminContext, Depends(require_permission("admins.read"))]
AdminsManageDep = Annotated[
    AdminContext,
    Depends(require_permission("admins.manage", step_up=True)),
]


class AdminCreateRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    role: str
    permission_overrides: dict[str, list[str]] = Field(default_factory=dict)
    support_notifications: bool = Field(default=False, strict=True)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in VALID_ADMIN_ROLES:
            raise ValueError("Unknown admin role")
        return value

    @field_validator("permission_overrides")
    @classmethod
    def validate_overrides(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if set(value) - {"allow", "deny"}:
            raise ValueError("Only allow/deny permission overrides are supported")
        for entries in value.values():
            if len(entries) > 100 or any(len(item) > 128 for item in entries):
                raise ValueError("Invalid permission override")
        return value


class AdminUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    permission_overrides: dict[str, list[str]] | None = None
    support_notifications: bool | None = Field(default=None, strict=True)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_ADMIN_ROLES:
            raise ValueError("Unknown admin role")
        return value

    @field_validator("permission_overrides")
    @classmethod
    def validate_overrides(
        cls, value: dict[str, list[str]] | None
    ) -> dict[str, list[str]] | None:
        if value is None:
            return value
        if set(value) - {"allow", "deny"}:
            raise ValueError("Only allow/deny permission overrides are supported")
        for entries in value.values():
            if len(entries) > 100 or any(len(item) > 128 for item in entries):
                raise ValueError("Invalid permission override")
        return value


def _admin_view(
    admin: AdminAccount, user: User, *, support_admin_ids: set[uuid.UUID] | None = None,
) -> dict[str, object]:
    return {
        "id": str(admin.id),
        "user_id": str(admin.user_id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "role": admin.role,
        "permissions": effective_permissions(admin),
        "permission_overrides": admin.permission_overrides,
        "is_active": admin.is_active,
        "support_notifications": admin.id in (support_admin_ids or set()),
        "support_notifications_effective": (
            admin.id in (support_admin_ids or set())
            and SupportRecipientConfigService.eligible(user, admin)
        ),
        "mfa_enabled": admin.mfa_enabled,
        "locked_until": admin.locked_until.isoformat() if admin.locked_until else None,
        "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        "created_at": admin.created_at.isoformat(),
    }


@router.get("/roles")
async def list_roles(context: AdminsReadDep) -> dict[str, object]:
    del context
    return {"roles": {role: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()}}


@router.get("/admins")
async def list_admins(context: AdminsReadDep, session: SessionDep) -> dict[str, object]:
    del context
    rows = (
        await session.execute(
            select(AdminAccount, User)
            .join(User, User.id == AdminAccount.user_id)
            .order_by(AdminAccount.created_at.asc())
        )
    ).all()
    policy = await SupportRecipientConfigService.policy(session)
    selected = SupportRecipientConfigService.admin_ids(policy)
    return {
        "items": [_admin_view(admin, user, support_admin_ids=selected) for admin, user in rows],
        "support_notifications_configured": policy is not None,
        "support_notifications_revision": SupportRecipientConfigService.revision(policy),
    }


@router.post("/admins", status_code=201)
async def create_admin(
    payload: AdminCreateRequest,
    request: Request,
    context: AdminsManageDep,
    session: SessionDep,
) -> dict[str, object]:
    if context.account.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner may create administrators")
    policy = await SupportRecipientConfigService.prepare_change(
        session, admin=context.account, initialize=True,
    )
    user = await session.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User must sign in to the product first")
    existing = await session.scalar(select(AdminAccount).where(AdminAccount.user_id == user.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Admin account already exists")
    admin = AdminAccount(
        user_id=user.id,
        role=payload.role,
        permission_overrides={} if payload.role == "owner" else payload.permission_overrides,
        is_active=True,
        created_by_admin_id=context.account.id,
    )
    session.add(admin)
    await session.flush()
    if policy is None:
        raise RuntimeError("Support recipient policy could not be initialized")
    try:
        await SupportRecipientConfigService.set_subscription(
            session, policy=policy, admin=context.account, account=admin, user=user,
            enabled=payload.support_notifications,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await AdminAuditService.record(
        session,
        action="admin.account.created",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="admin_account",
        resource_id=str(admin.id),
        metadata={
            "target_user_id": str(user.id), "role": admin.role,
            "support_notifications": payload.support_notifications,
        },
    )
    await session.commit()
    return _admin_view(admin, user, support_admin_ids=SupportRecipientConfigService.admin_ids(policy))


@router.patch("/admins/{admin_id}")
async def update_admin(
    admin_id: uuid.UUID,
    payload: AdminUpdateRequest,
    request: Request,
    context: AdminsManageDep,
    session: SessionDep,
) -> dict[str, object]:
    if context.account.role != "owner":
        raise HTTPException(status_code=403, detail="Only owner may manage administrators")
    policy = await SupportRecipientConfigService.prepare_change(
        session, admin=context.account, initialize=payload.support_notifications is not None,
    )
    target = await session.scalar(
        select(AdminAccount).where(AdminAccount.id == admin_id).with_for_update()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Admin account not found")
    user = await session.get(User, target.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Admin user missing")

    desired_role = payload.role or target.role
    desired_active = target.is_active if payload.is_active is None else payload.is_active
    if target.id == context.account.id and (desired_role != "owner" or not desired_active):
        raise HTTPException(status_code=409, detail="Owner cannot remove own active owner access")
    if target.role == "owner" and (desired_role != "owner" or not desired_active):
        owner_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(AdminAccount)
                    .where(AdminAccount.role == "owner", AdminAccount.is_active.is_(True))
                )
            )
            or 0
        )
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last active owner")

    before = {
        "role": target.role,
        "is_active": target.is_active,
        "permission_overrides": target.permission_overrides,
        "support_notifications": target.id in SupportRecipientConfigService.admin_ids(policy),
    }
    privilege_changed = False
    if payload.role is not None and payload.role != target.role:
        target.role = payload.role
        privilege_changed = True
    if payload.is_active is not None and payload.is_active != target.is_active:
        target.is_active = payload.is_active
        privilege_changed = True
    if payload.permission_overrides is not None:
        target.permission_overrides = payload.permission_overrides
        privilege_changed = True
    if target.role == "owner":
        target.permission_overrides = {}

    if payload.support_notifications is not None:
        if policy is None:
            raise RuntimeError("Support recipient policy could not be initialized")
        try:
            await SupportRecipientConfigService.set_subscription(
                session, policy=policy, admin=context.account, account=target, user=user,
                enabled=payload.support_notifications,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if privilege_changed:
        target.session_version += 1
        rows = list(
            (
                await session.scalars(
                    select(AdminSession).where(
                        AdminSession.admin_id == target.id,
                        AdminSession.revoked_at.is_(None),
                    )
                )
            ).all()
        )
        now = utcnow()
        for record in rows:
            record.revoked_at = now
            record.revoke_reason = "privilege_changed"

    await AdminAuditService.record(
        session,
        action="admin.account.updated",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="admin_account",
        resource_id=str(target.id),
        reason=payload.reason,
        metadata={
            "before": before,
            "after": {
                "role": target.role,
                "is_active": target.is_active,
                "permission_overrides": target.permission_overrides,
                "support_notifications": target.id in SupportRecipientConfigService.admin_ids(policy),
            },
            "sessions_revoked": privilege_changed,
        },
    )
    await session.commit()
    return _admin_view(target, user, support_admin_ids=SupportRecipientConfigService.admin_ids(policy))
