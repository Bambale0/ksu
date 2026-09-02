from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.admin_deps import AdminBaseDep
from app.api.deps import RedisDep, SessionDep
from app.core.config import settings
from app.db.models import AdminAccount, AdminSession
from app.services.admin_security import (
    AdminAuditService,
    AdminAuthService,
    AdminSecurityConfigurationError,
    effective_permissions,
    encrypt_mfa_secret,
    fingerprint,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    utcnow,
    verify_totp,
    decrypt_mfa_secret,
)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    otp: str | None = Field(default=None, min_length=6, max_length=6)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=64)


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class StepUpRequest(BaseModel):
    otp: str | None = Field(default=None, min_length=6, max_length=6)
    recovery_code: str | None = Field(default=None, min_length=8, max_length=64)


def _session_view(record: AdminSession, current_id: uuid.UUID) -> dict[str, object]:
    return {
        "id": str(record.id),
        "current": record.id == current_id,
        "created_at": record.created_at.isoformat(),
        "last_seen_at": record.last_seen_at.isoformat(),
        "expires_at": record.expires_at.isoformat(),
        "idle_expires_at": record.idle_expires_at.isoformat(),
        "mfa_verified": record.mfa_verified,
        "step_up_until": record.step_up_until.isoformat() if record.step_up_until else None,
        "revoked": record.revoked_at is not None,
    }


async def _enforce_mfa_rate_limit(redis: RedisDep, context: AdminBaseDep) -> None:
    """Share the MFA attempt budget across every session for one admin account."""

    await AdminAuthService.enforce_rate_limit(
        redis,
        key=f"admin:mfa:{context.account.id}",
        limit=settings.admin_login_rate_limit_per_minute,
    )


async def _lock_admin_for_recovery_code(
    session: SessionDep,
    admin_id: uuid.UUID,
) -> AdminAccount:
    """Serialize one-time recovery-code consumption and refresh stale identity state."""

    admin = await session.scalar(
        select(AdminAccount)
        .where(AdminAccount.id == admin_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=403, detail="Admin account unavailable")
    return admin


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")
    try:
        ip_hash = fingerprint(request.client.host if request.client else "unknown") or "unknown"
    except AdminSecurityConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await AdminAuthService.enforce_rate_limit(
        redis,
        key=f"admin:login:{ip_hash}",
        limit=settings.admin_login_rate_limit_per_minute,
    )
    telegram_user = AdminAuthService.parse_telegram_init_data(x_telegram_init_data)
    admin = await AdminAuthService.get_or_bootstrap_admin(session, telegram_user)
    if admin is None or not admin.is_active:
        await AdminAuditService.record(
            session,
            action="admin.login",
            outcome="denied",
            request=request,
            reason="No active admin account",
            metadata={"telegram_id_hash": fingerprint(str(telegram_user.id))},
        )
        await session.commit()
        raise HTTPException(status_code=403, detail="Admin access denied")

    if payload.recovery_code and admin.mfa_enabled:
        admin = await _lock_admin_for_recovery_code(session, admin.id)

    now = utcnow()
    if admin.locked_until is not None and admin.locked_until > now:
        await AdminAuditService.record(
            session,
            action="admin.login",
            outcome="denied",
            admin=admin,
            request=request,
            reason="Admin account temporarily locked",
        )
        await session.commit()
        raise HTTPException(status_code=429, detail="Admin login temporarily locked")

    mfa_verified = not settings.admin_require_mfa
    if admin.mfa_enabled:
        mfa_verified = AdminAuthService.verify_second_factor(
            admin,
            otp=payload.otp,
            recovery_code=payload.recovery_code,
        )
        if not mfa_verified:
            admin.failed_login_count += 1
            if admin.failed_login_count >= settings.admin_login_max_failures:
                admin.failed_login_count = 0
                admin.locked_until = now + timedelta(minutes=settings.admin_login_lock_minutes)
            await AdminAuditService.record(
                session,
                action="admin.login.mfa",
                outcome="failure",
                admin=admin,
                request=request,
                reason="Invalid second factor",
            )
            await session.commit()
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
    elif settings.admin_require_mfa:
        mfa_verified = False

    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = now
    admin.last_login_ip_hash = ip_hash
    record, token = await AdminAuthService.create_session(
        session,
        admin=admin,
        request=request,
        mfa_verified=mfa_verified,
    )
    await AdminAuditService.record(
        session,
        action="admin.login",
        outcome="success",
        admin=admin,
        admin_session=record,
        request=request,
        metadata={"mfa_verified": mfa_verified},
    )
    await session.commit()
    return {
        "token": token,
        "token_type": "bearer",
        "session_id": str(record.id),
        "expires_at": record.expires_at.isoformat(),
        "mfa_setup_required": settings.admin_require_mfa and not admin.mfa_enabled,
        "mfa_verified": record.mfa_verified,
        "role": admin.role,
        "permissions": effective_permissions(admin) if record.mfa_verified else [],
    }


@router.get("/me")
async def me(context: AdminBaseDep) -> dict[str, object]:
    return {
        "admin_id": str(context.account.id),
        "user_id": str(context.user.id),
        "telegram_id": context.user.telegram_id,
        "username": context.user.username,
        "role": context.account.role,
        "is_active": context.account.is_active,
        "mfa_enabled": context.account.mfa_enabled,
        "mfa_verified": context.session.mfa_verified,
        "step_up_until": (
            context.session.step_up_until.isoformat() if context.session.step_up_until else None
        ),
        "permissions": (
            effective_permissions(context.account) if context.session.mfa_verified else []
        ),
    }


@router.post("/mfa/setup")
async def setup_mfa(
    request: Request,
    context: AdminBaseDep,
    session: SessionDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if context.account.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA already enabled")
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Fresh Telegram initData required")
    telegram_user = AdminAuthService.parse_telegram_init_data(x_telegram_init_data)
    if telegram_user.id != context.user.telegram_id:
        raise HTTPException(status_code=403, detail="Identity mismatch")

    secret = generate_totp_secret()
    context.account.mfa_secret_encrypted = encrypt_mfa_secret(secret)
    context.account.recovery_code_hashes = []
    await AdminAuditService.record(
        session,
        action="admin.mfa.setup",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
    )
    await session.commit()
    return {
        "secret": secret,
        "otpauth_uri": provisioning_uri(secret, telegram_id=context.user.telegram_id),
    }


@router.post("/mfa/confirm")
async def confirm_mfa(
    payload: MfaConfirmRequest,
    request: Request,
    context: AdminBaseDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    await _enforce_mfa_rate_limit(redis, context)
    encrypted = context.account.mfa_secret_encrypted
    if not encrypted:
        raise HTTPException(status_code=409, detail="MFA setup has not started")
    secret = decrypt_mfa_secret(encrypted)
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    recovery_codes = generate_recovery_codes()
    context.account.mfa_enabled = True
    context.account.mfa_confirmed_at = utcnow()
    context.account.recovery_code_hashes = [hash_recovery_code(code) for code in recovery_codes]
    context.session.mfa_verified = True
    await AdminAuditService.record(
        session,
        action="admin.mfa.enabled",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
    )
    await session.commit()
    return {
        "mfa_enabled": True,
        "recovery_codes": recovery_codes,
        "warning": "Recovery codes are shown once. Store them securely.",
    }


@router.post("/step-up")
async def step_up(
    payload: StepUpRequest,
    request: Request,
    context: AdminBaseDep,
    session: SessionDep,
    redis: RedisDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not context.account.mfa_enabled:
        raise HTTPException(status_code=403, detail="MFA must be enabled")
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Fresh Telegram initData required")
    telegram_user = AdminAuthService.parse_telegram_init_data(x_telegram_init_data)
    if telegram_user.id != context.user.telegram_id:
        raise HTTPException(status_code=403, detail="Identity mismatch")
    await _enforce_mfa_rate_limit(redis, context)

    admin = context.account
    if payload.recovery_code:
        admin = await _lock_admin_for_recovery_code(session, admin.id)
        if not AdminAuthService.session_is_valid(context.session, admin):
            raise HTTPException(status_code=401, detail="Admin session expired")
        if not admin.mfa_enabled:
            raise HTTPException(status_code=403, detail="MFA must be enabled")

    if not AdminAuthService.verify_second_factor(
        admin,
        otp=payload.otp,
        recovery_code=payload.recovery_code,
    ):
        await AdminAuditService.record(
            session,
            action="admin.step_up",
            outcome="failure",
            admin=admin,
            admin_session=context.session,
            request=request,
            reason="Invalid second factor",
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid second factor")

    context.session.mfa_verified = True
    context.session.step_up_until = utcnow() + timedelta(minutes=settings.admin_step_up_minutes)
    await AdminAuditService.record(
        session,
        action="admin.step_up",
        outcome="success",
        admin=admin,
        admin_session=context.session,
        request=request,
    )
    await session.commit()
    return {"step_up_until": context.session.step_up_until.isoformat()}


@router.get("/sessions")
async def list_sessions(context: AdminBaseDep, session: SessionDep) -> dict[str, object]:
    rows = list(
        (
            await session.scalars(
                select(AdminSession)
                .where(AdminSession.admin_id == context.account.id)
                .order_by(AdminSession.created_at.desc())
                .limit(50)
            )
        ).all()
    )
    return {"sessions": [_session_view(row, context.session.id) for row in rows]}


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    context: AdminBaseDep,
    session: SessionDep,
) -> dict[str, bool]:
    record = await session.get(AdminSession, session_id)
    if record is None or record.admin_id != context.account.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if record.revoked_at is None:
        record.revoked_at = utcnow()
        record.revoke_reason = "self_revoked"
    await AdminAuditService.record(
        session,
        action="admin.session.revoked",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="admin_session",
        resource_id=str(record.id),
    )
    await session.commit()
    return {"revoked": True}


@router.post("/logout")
async def logout(
    request: Request,
    context: AdminBaseDep,
    session: SessionDep,
) -> dict[str, bool]:
    context.session.revoked_at = utcnow()
    context.session.revoke_reason = "logout"
    await AdminAuditService.record(
        session,
        action="admin.logout",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
    )
    await session.commit()
    return {"logged_out": True}
