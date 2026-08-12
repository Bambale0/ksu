from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import settings
from app.db.models import PartnerWithdrawal, ReferralReward, User
from app.db.payment_models import ReferralRewardReversal
from app.services.partner import (
    PartnerInsufficientFunds,
    PartnerService,
    PartnerWithdrawalBelowMinimum,
    PartnerWithdrawalError,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])


class CreateWithdrawalRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    requisites: str = Field(min_length=3, max_length=1000)


def _withdrawal_view(item: PartnerWithdrawal) -> dict[str, object]:
    return {
        "id": str(item.id),
        "amount": str(item.amount),
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "can_cancel": item.status == "pending",
    }


@router.get("/stats")
async def stats(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    first, second = await PartnerService.invitation_counts(session, user.id)
    accounting = await PartnerService.accounting(session, user.id)
    payload = f"ref_{user.telegram_id}"
    return {
        "first_line": first,
        "second_line": second,
        # Backward-compatible names used by the existing Profile shell.
        "available": str(accounting["available"]),
        "pending": str(accounting["pending_rewards"]),
        "total_earned": str(accounting["total_earned"]),
        "pending_withdrawals": str(accounting["pending_withdrawals"]),
        "minimum_withdrawal": str(max(Decimal("0"), settings.partner_min_withdrawal_rub)),
        "first_line_percent": str(settings.referral_first_percent),
        "second_line_percent": str(settings.referral_second_percent),
        "referral_payload": payload,
        "referral_link": PartnerService.referral_link(user.telegram_id),
    }


@router.get("/invitations")
async def invitations(
    user: CurrentUserDep,
    session: SessionDep,
    line: int | None = Query(default=None, ge=1, le=2),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    rows = await PartnerService.invitations(
        session,
        user_id=user.id,
        line=line,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "first_name": row["first_name"],
                "line": row["line"],
                "joined_at": row["joined_at"].isoformat(),
            }
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/rewards")
async def rewards(
    user: CurrentUserDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    reversal_total = (
        select(func.coalesce(func.sum(ReferralRewardReversal.amount), 0))
        .where(ReferralRewardReversal.reward_id == ReferralReward.id)
        .correlate(ReferralReward)
        .scalar_subquery()
    )
    stmt = (
        select(ReferralReward, User, reversal_total.label("reversed_amount"))
        .join(User, User.id == ReferralReward.source_user_id)
        .where(ReferralReward.partner_user_id == user.id)
    )
    if status_filter:
        stmt = stmt.where(ReferralReward.status == status_filter)
    rows = list(
        (
            await session.execute(
                stmt.order_by(ReferralReward.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": str(reward.id),
                "source_user": {
                    "username": source.username,
                    "first_name": source.first_name,
                },
                "line": reward.level,
                "percent": str(reward.percent),
                "amount": str(reward.amount),
                "reversed_amount": str(Decimal(reversed_amount or 0)),
                "net_amount": str(
                    max(Decimal("0"), Decimal(reward.amount) - Decimal(reversed_amount or 0))
                ),
                "status": reward.status,
                "created_at": reward.created_at.isoformat(),
            }
            for reward, source, reversed_amount in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/withdrawals")
async def withdrawals(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    rows = list(
        (
            await session.scalars(
                select(PartnerWithdrawal)
                .where(PartnerWithdrawal.user_id == user.id)
                .order_by(PartnerWithdrawal.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return {"items": [_withdrawal_view(item) for item in rows], "limit": limit, "offset": offset}


@router.post("/withdrawals", status_code=201)
async def create_withdrawal(
    payload: CreateWithdrawalRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        item = await PartnerService.create_withdrawal(
            session,
            user_id=user.id,
            amount=payload.amount,
            requisites=payload.requisites,
        )
    except PartnerWithdrawalBelowMinimum as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PartnerInsufficientFunds as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerWithdrawalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _withdrawal_view(item)


@router.post("/withdrawals/{withdrawal_id}/cancel")
async def cancel_withdrawal(
    withdrawal_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        item = await PartnerService.cancel_withdrawal(
            session,
            user_id=user.id,
            withdrawal_id=withdrawal_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Withdrawal not found") from exc
    except PartnerWithdrawalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _withdrawal_view(item)
