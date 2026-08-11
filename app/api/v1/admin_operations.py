from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import (
    Generation,
    PartnerWithdrawal,
    Payment,
    PromoCode,
    ReferralReward,
    SupportMessage,
    SupportTicket,
    User,
)
from app.services.admin_security import AdminAuditService, has_permission
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
PromosReadDep = Annotated[AdminContext, Depends(require_permission("promocodes.read"))]
PromosManageDep = Annotated[AdminContext, Depends(require_permission("promocodes.manage"))]
ReferralsReadDep = Annotated[AdminContext, Depends(require_permission("referrals.read"))]


class SupportReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class SupportStatusRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"]


class WithdrawalStatusRequest(BaseModel):
    status: Literal["processing", "paid", "rejected", "canceled"]
    reason: str = Field(min_length=3, max_length=500)


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    reward_credits: Decimal = Field(gt=0, le=100000)
    max_uses: int | None = Field(default=None, ge=1, le=10_000_000)
    expires_at: datetime | None = None


class PromoUpdateRequest(BaseModel):
    reward_credits: Decimal | None = Field(default=None, gt=0, le=100000)
    max_uses: int | None = Field(default=None, ge=1, le=10_000_000)
    is_active: bool | None = None
    expires_at: datetime | None = None


@router.get("/dashboard")
async def dashboard(context: DashboardDep, session: SessionDep) -> dict[str, object]:
    del context
    total_users = int((await session.scalar(select(func.count()).select_from(User))) or 0)
    active_users = int(
        (
            await session.scalar(
                select(func.count()).select_from(User).where(User.is_active.is_(True))
            )
        )
        or 0
    )
    queued_generations = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(Generation)
                .where(Generation.status.in_(["queued", "submitting", "generating", "retry"]))
            )
        )
        or 0
    )
    failed_generations = int(
        (
            await session.scalar(
                select(func.count()).select_from(Generation).where(Generation.status == "failed")
            )
        )
        or 0
    )
    open_tickets = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.status.in_(["open", "in_progress"]))
            )
        )
        or 0
    )
    pending_withdrawals = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(PartnerWithdrawal)
                .where(PartnerWithdrawal.status.in_(["pending", "processing"]))
            )
        )
        or 0
    )
    successful_payments = await session.execute(
        select(
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
            func.coalesce(func.sum(Payment.rox_amount), 0),
        ).where(Payment.status == "succeeded")
    )
    payment_count, payment_rub, payment_credits = successful_payments.one()
    return {
        "users": {"total": total_users, "active": active_users},
        "generations": {"active": queued_generations, "failed": failed_generations},
        "support": {"open": open_tickets},
        "withdrawals": {"pending_or_processing": pending_withdrawals},
        "payments": {
            "succeeded": int(payment_count or 0),
            "rub": str(payment_rub),
            "credits": str(payment_credits),
        },
    }


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
                stmt.order_by(Generation.created_at.desc()).offset(offset).limit(limit)
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
                stmt.order_by(Payment.created_at.desc()).offset(offset).limit(limit)
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


@router.get("/support/tickets")
async def list_support_tickets(
    context: SupportReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del context
    stmt = select(SupportTicket)
    if status_filter:
        stmt = stmt.where(SupportTicket.status == status_filter)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(SupportTicket.updated_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "topic": item.topic,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in rows
        ]
    }


@router.get("/support/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: uuid.UUID,
    context: SupportReadDep,
    session: SessionDep,
) -> dict[str, object]:
    del context
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    messages = list(
        (
            await session.scalars(
                select(SupportMessage)
                .where(SupportMessage.ticket_id == ticket_id)
                .order_by(SupportMessage.created_at.asc())
                .limit(500)
            )
        ).all()
    )
    return {
        "id": str(ticket.id),
        "user_id": str(ticket.user_id),
        "topic": ticket.topic,
        "status": ticket.status,
        "messages": [
            {
                "id": str(message.id),
                "sender_user_id": str(message.user_id) if message.user_id else None,
                "is_admin": message.is_admin,
                "body": message.body,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
async def reply_support_ticket(
    ticket_id: uuid.UUID,
    payload: SupportReplyRequest,
    request: Request,
    context: SupportManageDep,
    session: SessionDep,
) -> dict[str, str]:
    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.id == ticket_id).with_for_update()
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "closed":
        raise HTTPException(status_code=409, detail="Ticket is closed")
    message = SupportMessage(
        ticket_id=ticket.id,
        user_id=context.user.id,
        is_admin=True,
        body=payload.body.strip(),
    )
    session.add(message)
    if ticket.status == "open":
        ticket.status = "in_progress"
    await session.flush()
    await AdminAuditService.record(
        session,
        action="admin.support.replied",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="support_ticket",
        resource_id=str(ticket.id),
        metadata={"message_id": str(message.id)},
    )
    await session.commit()
    return {"message_id": str(message.id), "status": ticket.status}


@router.patch("/support/tickets/{ticket_id}/status")
async def update_support_status(
    ticket_id: uuid.UUID,
    payload: SupportStatusRequest,
    request: Request,
    context: SupportManageDep,
    session: SessionDep,
) -> dict[str, str]:
    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.id == ticket_id).with_for_update()
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    before = ticket.status
    ticket.status = payload.status
    await AdminAuditService.record(
        session,
        action="admin.support.status_changed",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="support_ticket",
        resource_id=str(ticket.id),
        metadata={"before": before, "after": payload.status},
    )
    await session.commit()
    return {"id": str(ticket.id), "status": ticket.status}


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
                stmt.order_by(PartnerWithdrawal.created_at.desc()).offset(offset).limit(limit)
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


@router.get("/promocodes")
async def list_promocodes(
    context: PromosReadDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, object]:
    del context
    rows = list(
        (
            await session.scalars(
                select(PromoCode).order_by(PromoCode.created_at.desc()).limit(limit)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "code": item.code,
                "reward_credits": str(item.reward_amount),
                "max_uses": item.max_uses,
                "uses_count": item.uses_count,
                "is_active": item.is_active,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ]
    }


@router.post("/promocodes", status_code=201)
async def create_promocode(
    payload: PromoCreateRequest,
    request: Request,
    context: PromosManageDep,
    session: SessionDep,
) -> dict[str, object]:
    code = payload.code.upper()
    existing = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Promo code already exists")
    promo = PromoCode(
        code=code,
        reward_amount=payload.reward_credits,
        max_uses=payload.max_uses,
        is_active=True,
        expires_at=payload.expires_at,
    )
    session.add(promo)
    await session.flush()
    await AdminAuditService.record(
        session,
        action="admin.promocode.created",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="promo_code",
        resource_id=str(promo.id),
        metadata={
            "code": promo.code,
            "reward_credits": str(promo.reward_amount),
            "max_uses": promo.max_uses,
        },
    )
    await session.commit()
    return {"id": str(promo.id), "code": promo.code}


@router.patch("/promocodes/{promo_id}")
async def update_promocode(
    promo_id: uuid.UUID,
    payload: PromoUpdateRequest,
    request: Request,
    context: PromosManageDep,
    session: SessionDep,
) -> dict[str, object]:
    promo = await session.scalar(select(PromoCode).where(PromoCode.id == promo_id).with_for_update())
    if promo is None:
        raise HTTPException(status_code=404, detail="Promo code not found")
    changes: dict[str, object] = {}
    if payload.reward_credits is not None:
        changes["reward_credits"] = [str(promo.reward_amount), str(payload.reward_credits)]
        promo.reward_amount = payload.reward_credits
    if payload.max_uses is not None:
        if payload.max_uses < promo.uses_count:
            raise HTTPException(status_code=409, detail="max_uses cannot be below uses_count")
        changes["max_uses"] = [promo.max_uses, payload.max_uses]
        promo.max_uses = payload.max_uses
    if payload.is_active is not None:
        changes["is_active"] = [promo.is_active, payload.is_active]
        promo.is_active = payload.is_active
    if payload.expires_at is not None:
        changes["expires_at"] = [
            promo.expires_at.isoformat() if promo.expires_at else None,
            payload.expires_at.isoformat(),
        ]
        promo.expires_at = payload.expires_at
    await AdminAuditService.record(
        session,
        action="admin.promocode.updated",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="promo_code",
        resource_id=str(promo.id),
        metadata={"changes": changes},
    )
    await session.commit()
    return {"id": str(promo.id), "updated": True}


@router.get("/referrals/rewards")
async def list_referral_rewards(
    context: ReferralsReadDep,
    session: SessionDep,
    partner_user_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, object]:
    del context
    stmt = select(ReferralReward)
    if partner_user_id:
        stmt = stmt.where(ReferralReward.partner_user_id == partner_user_id)
    if status_filter:
        stmt = stmt.where(ReferralReward.status == status_filter)
    rows = list(
        (
            await session.scalars(stmt.order_by(ReferralReward.created_at.desc()).limit(limit))
        ).all()
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "partner_user_id": str(item.partner_user_id),
                "source_user_id": str(item.source_user_id),
                "level": item.level,
                "percent": str(item.percent),
                "amount": str(item.amount),
                "status": item.status,
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ]
    }
