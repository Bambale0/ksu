from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import RedisDep, SessionDep
from app.core.config import settings
from app.db.models import AdminAccount, AdminSession, User
from app.services.admin_policy import AdminPolicy
from app.services.admin_security import (
    AdminAuditService,
    AdminAuthService,
    AdminSecurityConfigurationError,
    fingerprint,
    hash_admin_token,
    utcnow,
)


@dataclass(slots=True)
class AdminContext:
    account: AdminAccount
    session: AdminSession
    user: User


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing admin authorization")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid admin authorization")
    return token


async def get_admin_context_base(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminContext:
    token = _bearer_token(authorization)
    try:
        token_hash = hash_admin_token(token)
    except AdminSecurityConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    record = await session.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash).with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid admin session")
    admin = await session.get(AdminAccount, record.admin_id)
    if admin is None or not AdminAuthService.session_is_valid(record, admin):
        if record.revoked_at is None:
            record.revoked_at = utcnow()
            record.revoke_reason = "expired_or_invalid"
            await session.commit()
        raise HTTPException(status_code=401, detail="Admin session expired")

    user = await session.get(User, admin.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Admin account unavailable")

    await AdminAuthService.enforce_rate_limit(
        redis,
        key=f"admin:req:{record.id}",
        limit=settings.admin_request_rate_limit_per_minute,
    )

    ua_hash = fingerprint(request.headers.get("user-agent"))
    if record.user_agent_hash and ua_hash and record.user_agent_hash != ua_hash:
        record.revoked_at = utcnow()
        record.revoke_reason = "user_agent_changed"
        await AdminAuditService.record(
            session,
            action="admin.session.user_agent_changed",
            outcome="denied",
            admin=admin,
            admin_session=record,
            request=request,
            reason="Session fingerprint mismatch",
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Admin session invalidated")

    ip_hash = fingerprint(request.client.host if request.client else None)
    if record.ip_hash and ip_hash and record.ip_hash != ip_hash:
        record.ip_hash = ip_hash
        record.step_up_until = None
        await AdminAuditService.record(
            session,
            action="admin.session.ip_changed",
            outcome="success",
            admin=admin,
            admin_session=record,
            request=request,
            reason="Step-up was cleared after network change",
        )

    now = utcnow()
    record.last_seen_at = now
    record.idle_expires_at = min(
        record.expires_at,
        now + timedelta(minutes=settings.admin_idle_timeout_minutes),
    )
    await session.commit()
    return AdminContext(account=admin, session=record, user=user)


AdminBaseDep = Annotated[AdminContext, Depends(get_admin_context_base)]


async def get_verified_admin(context: AdminBaseDep) -> AdminContext:
    if settings.admin_require_mfa and not context.session.mfa_verified:
        raise HTTPException(status_code=403, detail="Admin MFA verification required")
    return context


VerifiedAdminDep = Annotated[AdminContext, Depends(get_verified_admin)]


def require_permission(permission: str, *, step_up: bool = False) -> Callable[..., AdminContext]:
    async def dependency(
        request: Request,
        context: VerifiedAdminDep,
        session: SessionDep,
    ) -> AdminContext:
        if not AdminPolicy.has_permission(context.account, permission):
            await AdminAuditService.record(
                session,
                action="admin.authorization.denied",
                outcome="denied",
                admin=context.account,
                admin_session=context.session,
                request=request,
                reason=f"Missing permission: {permission}",
                metadata={"permission": permission},
            )
            await session.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        if step_up and not AdminAuthService.step_up_valid(context.session):
            await AdminAuditService.record(
                session,
                action="admin.step_up.required",
                outcome="denied",
                admin=context.account,
                admin_session=context.session,
                request=request,
                reason=f"Sensitive permission requires step-up: {permission}",
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fresh MFA step-up required",
            )
        return context

    return dependency
