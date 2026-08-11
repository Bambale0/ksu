from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import AdminAccount, AdminAuditLog, AdminSession
from app.services.admin_security import audit_integrity_hash, utcnow

router = APIRouter(prefix="/admin", tags=["admin-audit"])

AuditReadDep = Annotated[AdminContext, Depends(require_permission("audit.read"))]
SecurityReadDep = Annotated[AdminContext, Depends(require_permission("security.read"))]


def _integrity_payload(row: AdminAuditLog) -> dict[str, Any]:
    return {
        "admin_id": str(row.admin_id) if row.admin_id else None,
        "session_id": str(row.session_id) if row.session_id else None,
        "action": row.action,
        "outcome": row.outcome,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "reason": row.reason,
        "request_id": row.request_id,
        "ip_hash": row.ip_hash,
        "user_agent_hash": row.user_agent_hash,
        "metadata": row.metadata_json,
    }


@router.get("/audit")
async def list_audit(
    context: AuditReadDep,
    session: SessionDep,
    action: str | None = Query(default=None, max_length=128),
    outcome: str | None = Query(default=None, max_length=24),
    admin_id: uuid.UUID | None = None,
    resource_type: str | None = Query(default=None, max_length=64),
    resource_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del context
    stmt = select(AdminAuditLog)
    conditions = []
    if action:
        conditions.append(AdminAuditLog.action == action)
    if outcome:
        conditions.append(AdminAuditLog.outcome == outcome)
    if admin_id:
        conditions.append(AdminAuditLog.admin_id == admin_id)
    if resource_type:
        conditions.append(AdminAuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AdminAuditLog.resource_id == resource_id)
    if conditions:
        stmt = stmt.where(*conditions)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    items = []
    for row in rows:
        integrity_valid = audit_integrity_hash(_integrity_payload(row)) == row.integrity_hash
        items.append(
            {
                "id": str(row.id),
                "admin_id": str(row.admin_id) if row.admin_id else None,
                "session_id": str(row.session_id) if row.session_id else None,
                "action": row.action,
                "outcome": row.outcome,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "reason": row.reason,
                "request_id": row.request_id,
                "metadata": row.metadata_json,
                "integrity_valid": integrity_valid,
                "created_at": row.created_at.isoformat(),
            }
        )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/security/overview")
async def security_overview(
    context: SecurityReadDep,
    session: SessionDep,
) -> dict[str, object]:
    del context
    now = utcnow()
    since = now - timedelta(hours=24)
    active_sessions = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(AdminSession)
                .where(
                    AdminSession.revoked_at.is_(None),
                    AdminSession.expires_at > now,
                    AdminSession.idle_expires_at > now,
                )
            )
        )
        or 0
    )
    failed_logins = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(AdminAuditLog)
                .where(
                    AdminAuditLog.created_at >= since,
                    AdminAuditLog.action.in_(["admin.login", "admin.login.mfa", "admin.step_up"]),
                    AdminAuditLog.outcome.in_(["failure", "denied"]),
                )
            )
        )
        or 0
    )
    locked_admins = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(AdminAccount)
                .where(AdminAccount.locked_until > now)
            )
        )
        or 0
    )
    mfa_missing = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(AdminAccount)
                .where(AdminAccount.is_active.is_(True), AdminAccount.mfa_enabled.is_(False))
            )
        )
        or 0
    )
    return {
        "active_sessions": active_sessions,
        "failed_or_denied_auth_events_24h": failed_logins,
        "locked_admins": locked_admins,
        "active_admins_without_mfa": mfa_missing,
    }


@router.get("/security/sessions")
async def list_all_sessions(
    context: SecurityReadDep,
    session: SessionDep,
    active_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    del context
    stmt = select(AdminSession).order_by(AdminSession.last_seen_at.desc()).limit(limit)
    if active_only:
        now = utcnow()
        stmt = stmt.where(
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
            AdminSession.idle_expires_at > now,
        )
    rows = list((await session.scalars(stmt)).all())
    return {
        "items": [
            {
                "id": str(row.id),
                "admin_id": str(row.admin_id),
                "created_at": row.created_at.isoformat(),
                "last_seen_at": row.last_seen_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
                "idle_expires_at": row.idle_expires_at.isoformat(),
                "mfa_verified": row.mfa_verified,
                "step_up_until": row.step_up_until.isoformat() if row.step_up_until else None,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "revoke_reason": row.revoke_reason,
            }
            for row in rows
        ]
    }
