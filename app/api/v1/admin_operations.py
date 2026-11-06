from __future__ import annotations

import uuid
from collections.abc import Awaitable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import (
    Generation,
    PartnerWithdrawal,
    Payment,
    ReferralReward,
)
from app.services.admin_security import AdminAuditService, has_permission
from app.services.admin_commands import AdminCommandInProgress, AdminCommandStoredFailure, AdminIdempotencyConflict
from app.services.admin_policy import AdminPolicyError
from app.services.admin_support import AdminSupportService, SupportTicketClosedError
from app.services.admin_reporting import AdminReportingService
from app.services.generation_provider import GenerationProviderService

router = APIRouter(prefix="/admin", tags=["admin-operations"])

DashboardDep = Annotated[AdminContext, Depends(require_permission("dashboard.read"))]
GenerationsReadDep = Annotated[AdminContext, Depends(require_permission("generations.read"))]
GenerationsManageDep = Annotated[
    AdminContext,
    Depends(require_permission("generations.manage")),
]
PaymentsReadDep = Annotated[AdminContext, Depends(require_permission("payments.read"))]
SupportReadDep = Annotated[AdminContext, Depends(require_permission("support.read"))]
SupportManageDep = Annotated[AdminContext, Depends(require_permission("support.manage"))]
WithdrawalsReadDep = Annotated[AdminContext, Depends(require_permission("withdrawals.read"))]
WithdrawalsManageDep = Annotated[
    AdminContext,
    Depends(require_permission("withdrawals.manage", step_up=True)),
]
ReferralsReadDep = Annotated[AdminContext, Depends(require_permission("referrals.read"))]


class SupportReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class SupportStatusRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"]


class WithdrawalStatusRequest(BaseModel):
    status: Literal["processing", "paid", "rejected", "canceled"]
    reason: str = Field(min_length=3, max_length=500)


@router.get("/dashboard")
async def dashboard(context: DashboardDep, session: SessionDep) -> dict[str, object]:
    return await AdminReportingService.summary(session, admin=context.account)


@router.get("/generations")
async def list_generations(
    context: GenerationsReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del context
    stmt = select(Generation)
    count_stmt = select(func.count()).select_from(Generation)
    conditions = []
    if status_filter:
        conditions.append(Generation.status == status_filter)
    if user_id:
        conditions.append(Generation.user_id == user_id)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(Generation.created_at.desc(), Generation.id.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    total = int((await session.scalar(count_stmt)) or 0)
    return {
        "items": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "model_id": (item.parameters or {}).get("_model_id"),
                "kind": item.kind,
                "status": item.status,
                "provider": item.provider,
                "external_id": item.external_id,
                "cost_credits": str(item.cost_rox),
                "prompt": item.prompt[:1000],
                "input_url": item.input_url,
                "result_url": item.result_url,
                "error": item.error[:1000] if item.error else None,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/generations/{generation_id}/reconcile")
async def reconcile_generation(
    generation_id: uuid.UUID,
    request: Request,
    context: GenerationsManageDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await session.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    if generation.provider != "kie" or not generation.external_id:
        raise HTTPException(status_code=409, detail="Generation has no Kie task to reconcile")
    updated = await GenerationProviderService.sync_kie_task(
        session,
        task_id=generation.external_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Generation task not found")
    await AdminAuditService.record(
        session,
        action="admin.generation.reconciled",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="generation",
        resource_id=str(generation_id),
        metadata={"status": updated.status},
    )
    await session.commit()
    return {"id": str(updated.id), "status": updated.status}


@router.get("/payments")
async def list_payments(
    context: PaymentsReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    provider: str | None = Query(default=None, max_length=64),
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del context
    stmt = select(Payment)
    count_stmt = select(func.count()).select_from(Payment)
    conditions = []
    if status_filter:
        conditions.append(Payment.status == status_filter)
    if provider:
        conditions.append(Payment.provider == provider)
    if user_id:
        conditions.append(Payment.user_id == user_id)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(Payment.created_at.desc(), Payment.id.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    total = int((await session.scalar(count_stmt)) or 0)
    return {
        "items": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "provider": item.provider,
                "external_id": item.external_id,
                "amount": str(item.amount),
                "currency": item.currency,
                "credits": str(item.rox_amount),
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in rows
        ],
        "total": total,
    }


def _support_idempotency(value: str | None) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 160:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key is required")
    return key


def _support_request_id(request: Request) -> str:
    return str(request.headers.get("X-Request-Id") or f"support:{uuid.uuid4()}")[:64]


async def _support_commit(
    session: SessionDep, operation: Awaitable[tuple[dict[str, Any], bool]],
) -> tuple[dict[str, Any], bool]:
    try:
        result = await operation
        await session.commit()
        return result
    except (LookupError, AdminPolicyError, ValueError, AdminIdempotencyConflict,
            AdminCommandInProgress, AdminCommandStoredFailure) as exc:
        await session.rollback()
        if isinstance(exc, LookupError):
            status_code = 404
        elif isinstance(exc, AdminPolicyError):
            status_code = 403
        elif isinstance(exc, SupportTicketClosedError):
            status_code = 409
        elif isinstance(exc, ValueError):
            status_code = 422
        else:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/support/tickets")
async def list_support_tickets(
    context: SupportReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    q: str | None = Query(default=None, max_length=128),
) -> dict[str, Any]:
    return await AdminSupportService.list_tickets(
        session, admin=context.account, status=status_filter, q=q, limit=limit, offset=offset,
    )


@router.get("/support/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: uuid.UUID,
    context: SupportReadDep,
    session: SessionDep,
    message_limit: int = Query(default=100, ge=1, le=500),
    before: uuid.UUID | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return await AdminSupportService.get_ticket(
            session, admin=context.account, ticket_id=ticket_id,
            message_limit=message_limit, before=before,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
async def reply_support_ticket(
    ticket_id: uuid.UUID,
    payload: SupportReplyRequest,
    request: Request,
    context: SupportManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    key = _support_idempotency(idempotency_key)
    confirmed = str(confirmation or "").strip().lower() in {"1", "true", "yes", "confirm", "confirmed"}
    result, replayed = await _support_commit(
        session,
        AdminSupportService.reply_ticket(
            session, admin=context.account, ticket_id=ticket_id, body=payload.body,
            idempotency_key=key, request_id=_support_request_id(request), confirmed=confirmed,
            request=request, admin_session=context.session,
        ),
    )
    return {**result, "status": result["ticket_status"], "idempotency_replayed": replayed}


@router.patch("/support/tickets/{ticket_id}/status")
async def update_support_status(
    ticket_id: uuid.UUID,
    payload: SupportStatusRequest,
    request: Request,
    context: SupportManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, replayed = await _support_commit(
        session,
        AdminSupportService.update_ticket(
            session, admin=context.account, ticket_id=ticket_id,
            status=payload.status, priority=None,
            idempotency_key=_support_idempotency(idempotency_key),
            request_id=_support_request_id(request),
            request=request, admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/withdrawals")
async def list_withdrawals(
    context: WithdrawalsReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    stmt = select(PartnerWithdrawal)
    if status_filter:
        stmt = stmt.where(PartnerWithdrawal.status == status_filter)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(PartnerWithdrawal.created_at.desc(), PartnerWithdrawal.id.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    can_manage = has_permission(context.account, "withdrawals.manage")
    return {
        "items": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "amount": str(item.amount),
                "status": item.status,
                "requisites": item.requisites if can_manage else "[restricted]",
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in rows
        ]
    }


@router.patch("/withdrawals/{withdrawal_id}/status")
async def update_withdrawal_status(
    withdrawal_id: uuid.UUID,
    payload: WithdrawalStatusRequest,
    request: Request,
    context: WithdrawalsManageDep,
    session: SessionDep,
) -> dict[str, str]:
    withdrawal = await session.scalar(
        select(PartnerWithdrawal)
        .where(PartnerWithdrawal.id == withdrawal_id)
        .with_for_update()
    )
    if withdrawal is None:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    transitions = {
        "pending": {"processing", "rejected", "canceled"},
        "processing": {"paid", "rejected", "canceled"},
        "paid": set(),
        "rejected": set(),
        "canceled": set(),
    }
    allowed = transitions.get(withdrawal.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid withdrawal transition: {withdrawal.status} -> {payload.status}",
        )
    before = withdrawal.status
    withdrawal.status = payload.status
    await AdminAuditService.record(
        session,
        action="admin.withdrawal.status_changed",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="partner_withdrawal",
        resource_id=str(withdrawal.id),
        reason=payload.reason,
        metadata={"before": before, "after": payload.status, "amount": str(withdrawal.amount)},
    )
    await session.commit()
    return {"id": str(withdrawal.id), "status": withdrawal.status}


@router.get("/referrals/rewards")
async def list_referral_rewards(
    context: ReferralsReadDep,
    session: SessionDep,
    partner_user_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del context
    filters = []
    if partner_user_id:
        filters.append(ReferralReward.partner_user_id == partner_user_id)
    if status_filter:
        filters.append(ReferralReward.status == status_filter)
    total = int((await session.scalar(
        select(func.count()).select_from(ReferralReward).where(*filters)
    )) or 0)
    rows = list((await session.scalars(
        select(ReferralReward).where(*filters)
        .order_by(ReferralReward.created_at.desc(), ReferralReward.id.desc())
        .offset(offset).limit(limit)
    )).all())
    return {
        "items": [
            {
                "id": str(item.id),
                "partner_user_id": str(item.partner_user_id),
                "source_user_id": str(item.source_user_id),
                "source_transaction_id": str(item.source_transaction_id),
                "reason": item.reason,
                "promo_id": str(item.promo_id) if item.promo_id else None,
                "promo_code": item.promo_code,
                "payment_id": str(item.payment_id) if item.payment_id else None,
                "level": item.level,
                "percent": str(item.percent),
                "amount": str(item.amount),
                "status": item.status,
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ],
        "total": total, "limit": limit, "offset": offset,
        "has_more": offset + len(rows) < total,
    }
