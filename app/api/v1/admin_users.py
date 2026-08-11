from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import (
    AdminAccount,
    AdminUserNote,
    Generation,
    Payment,
    SupportTicket,
    User,
    Wallet,
    WalletTransaction,
)
from app.services.admin_security import AdminAuditService, has_permission
from app.services.credits import InternalCreditService
from app.services.wallet import InsufficientBalanceError, WalletService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

UsersReadDep = Annotated[AdminContext, Depends(require_permission("users.read"))]
UsersManageDep = Annotated[AdminContext, Depends(require_permission("users.manage"))]
WalletAdjustDep = Annotated[
    AdminContext,
    Depends(require_permission("users.wallet.adjust", step_up=True)),
]
UserNotesDep = Annotated[AdminContext, Depends(require_permission("users.notes"))]


class UserStatusRequest(BaseModel):
    is_active: bool
    reason: str = Field(min_length=5, max_length=500)


class WalletAdjustmentRequest(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=5, max_length=500)


class UserNoteRequest(BaseModel):
    body: str = Field(min_length=2, max_length=4000)


def _masked_telegram_id(value: int) -> str:
    text = str(value)
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"


def _user_view(
    user: User,
    *,
    balance: Decimal | None,
    can_view_pii: bool,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(user.id),
        "username": user.username if can_view_pii else None,
        "first_name": user.first_name if can_view_pii else "[restricted]",
        "last_name": user.last_name if can_view_pii else None,
        "telegram_id": user.telegram_id if can_view_pii else _masked_telegram_id(user.telegram_id),
        "is_active": user.is_active,
        "balance_credits": str(balance or Decimal("0")),
        "balance_rub": str(InternalCreditService.rubles_for(balance or Decimal("0"))),
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }
    return result


@router.get("")
async def list_users(
    context: UsersReadDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=128),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    can_pii = has_permission(context.account, "users.pii")
    stmt = select(User, Wallet.balance).outerjoin(Wallet, Wallet.user_id == User.id)
    count_stmt = select(func.count()).select_from(User)
    conditions = []
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if q:
        search = q.strip()
        text_condition = or_(
            User.username.ilike(f"%{search}%"),
            User.first_name.ilike(f"%{search}%"),
            User.last_name.ilike(f"%{search}%"),
        )
        if search.isdigit():
            text_condition = or_(text_condition, User.telegram_id == int(search))
        conditions.append(text_condition)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)

    rows = (
        await session.execute(
            stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
    ).all()
    total = int((await session.scalar(count_stmt)) or 0)
    return {
        "items": [
            _user_view(user, balance=balance, can_view_pii=can_pii)
            for user, balance in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    context: UsersReadDep,
    session: SessionDep,
) -> dict[str, object]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    wallet = await session.get(Wallet, user_id)
    can_pii = has_permission(context.account, "users.pii")

    generations = int(
        (await session.scalar(select(func.count()).select_from(Generation).where(Generation.user_id == user_id)))
        or 0
    )
    payments = int(
        (await session.scalar(select(func.count()).select_from(Payment).where(Payment.user_id == user_id)))
        or 0
    )
    tickets = int(
        (
            await session.scalar(
                select(func.count()).select_from(SupportTicket).where(SupportTicket.user_id == user_id)
            )
        )
        or 0
    )
    admin_account = await session.scalar(
        select(AdminAccount).where(AdminAccount.user_id == user_id)
    )
    result = _user_view(
        user,
        balance=Decimal(wallet.balance) if wallet else Decimal("0"),
        can_view_pii=can_pii,
    )
    result["stats"] = {
        "generations": generations,
        "payments": payments,
        "support_tickets": tickets,
    }
    result["is_admin"] = admin_account is not None and admin_account.is_active
    return result


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusRequest,
    request: Request,
    context: UsersManageDep,
    session: SessionDep,
) -> dict[str, object]:
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    target_admin = await session.scalar(
        select(AdminAccount).where(AdminAccount.user_id == user_id)
    )
    if target_admin is not None and target_admin.is_active:
        if context.account.role != "owner":
            raise HTTPException(status_code=403, detail="Only owner may change an admin user")
        from app.services.admin_security import AdminAuthService

        if not AdminAuthService.step_up_valid(context.session):
            raise HTTPException(status_code=403, detail="Fresh MFA step-up required")
        if target_admin.id == context.account.id and payload.is_active is False:
            raise HTTPException(status_code=409, detail="Cannot deactivate your own owner user")

    before = user.is_active
    user.is_active = payload.is_active
    await AdminAuditService.record(
        session,
        action="admin.user.status_changed",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="user",
        resource_id=str(user.id),
        reason=payload.reason,
        metadata={"before": before, "after": payload.is_active},
    )
    await session.commit()
    return {"id": str(user.id), "is_active": user.is_active}


@router.post("/{user_id}/wallet-adjustments")
async def adjust_wallet(
    user_id: uuid.UUID,
    payload: WalletAdjustmentRequest,
    request: Request,
    context: WalletAdjustDep,
    session: SessionDep,
) -> dict[str, str]:
    if payload.amount == 0:
        raise HTTPException(status_code=422, detail="Adjustment amount cannot be zero")
    if abs(payload.amount) > Decimal("100000"):
        raise HTTPException(status_code=422, detail="Adjustment exceeds safety limit")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        if payload.amount > 0:
            tx = await WalletService.credit(
                session,
                user_id=user.id,
                amount=payload.amount,
                kind="admin_adjustment",
                reference_type="admin",
                reference_id=str(context.account.id),
                idempotency_key=f"admin-wallet:{request_id}",
            )
        else:
            tx = await WalletService.debit(
                session,
                user_id=user.id,
                amount=abs(payload.amount),
                kind="admin_adjustment",
                reference_type="admin",
                reference_id=str(context.account.id),
                idempotency_key=f"admin-wallet:{request_id}",
            )
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient user balance") from exc

    await AdminAuditService.record(
        session,
        action="admin.wallet.adjusted",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="user",
        resource_id=str(user.id),
        reason=payload.reason,
        metadata={
            "transaction_id": str(tx.id),
            "amount_credits": str(payload.amount),
            "balance_before": str(tx.balance_before),
            "balance_after": str(tx.balance_after),
        },
    )
    await session.commit()
    return {
        "transaction_id": str(tx.id),
        "balance_before": str(tx.balance_before),
        "balance_after": str(tx.balance_after),
    }


@router.post("/{user_id}/notes", status_code=201)
async def add_user_note(
    user_id: uuid.UUID,
    payload: UserNoteRequest,
    request: Request,
    context: UserNotesDep,
    session: SessionDep,
) -> dict[str, str]:
    if await session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    note = AdminUserNote(user_id=user_id, admin_id=context.account.id, body=payload.body.strip())
    session.add(note)
    await session.flush()
    await AdminAuditService.record(
        session,
        action="admin.user.note_added",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="user",
        resource_id=str(user_id),
        metadata={"note_id": str(note.id)},
    )
    await session.commit()
    return {"id": str(note.id)}


@router.get("/{user_id}/history")
async def user_history(
    user_id: uuid.UUID,
    context: UsersReadDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, object]:
    if await session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")

    per_source = max(10, min(limit, 50))
    events: list[dict[str, object]] = []

    txs = list(
        (
            await session.scalars(
                select(WalletTransaction)
                .where(WalletTransaction.user_id == user_id)
                .order_by(WalletTransaction.created_at.desc())
                .limit(per_source)
            )
        ).all()
    )
    for tx in txs:
        events.append(
            {
                "type": "wallet",
                "id": str(tx.id),
                "at": tx.created_at,
                "kind": tx.kind,
                "amount": str(tx.amount),
                "balance_after": str(tx.balance_after),
            }
        )

    generations = list(
        (
            await session.scalars(
                select(Generation)
                .where(Generation.user_id == user_id)
                .order_by(Generation.created_at.desc())
                .limit(per_source)
            )
        ).all()
    )
    for item in generations:
        events.append(
            {
                "type": "generation",
                "id": str(item.id),
                "at": item.created_at,
                "status": item.status,
                "model_id": (item.parameters or {}).get("_model_id"),
                "cost_credits": str(item.cost_rox),
                "prompt": item.prompt[:500],
            }
        )

    payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(Payment.user_id == user_id)
                .order_by(Payment.created_at.desc())
                .limit(per_source)
            )
        ).all()
    )
    for item in payments:
        events.append(
            {
                "type": "payment",
                "id": str(item.id),
                "at": item.created_at,
                "provider": item.provider,
                "status": item.status,
                "amount": str(item.amount),
                "currency": item.currency,
                "credits": str(item.rox_amount),
            }
        )

    tickets = list(
        (
            await session.scalars(
                select(SupportTicket)
                .where(SupportTicket.user_id == user_id)
                .order_by(SupportTicket.created_at.desc())
                .limit(per_source)
            )
        ).all()
    )
    for item in tickets:
        events.append(
            {
                "type": "support_ticket",
                "id": str(item.id),
                "at": item.created_at,
                "topic": item.topic,
                "status": item.status,
            }
        )

    if has_permission(context.account, "users.notes"):
        notes = list(
            (
                await session.scalars(
                    select(AdminUserNote)
                    .where(AdminUserNote.user_id == user_id)
                    .order_by(AdminUserNote.created_at.desc())
                    .limit(per_source)
                )
            ).all()
        )
        for note in notes:
            events.append(
                {
                    "type": "admin_note",
                    "id": str(note.id),
                    "at": note.created_at,
                    "admin_id": str(note.admin_id) if note.admin_id else None,
                    "body": note.body,
                }
            )

    events.sort(key=lambda event: event["at"], reverse=True)  # type: ignore[arg-type]
    for event in events:
        at = event["at"]
        event["at"] = at.isoformat()  # type: ignore[union-attr]

    return {"items": events[:limit]}
