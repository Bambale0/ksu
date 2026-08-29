from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import settings
from app.db.feed_models import FeedRemixEvent
from app.db.models import Generation, PartnerWithdrawal, ReferralReward, User, Wallet
from app.db.partner_wallet_models import PartnerWalletTransfer
from app.db.payment_models import ReferralRewardReversal
from app.services.credits import InternalCreditService
from app.services.partner import (
    PartnerInsufficientFunds,
    PartnerService,
    PartnerWithdrawalBelowMinimum,
    PartnerWithdrawalError,
    PartnerWithdrawalIdempotencyConflict,
)
from app.services.partner_wallet import (
    PartnerWalletTransferError,
    PartnerWalletTransferInsufficientFunds,
    PartnerWalletTransferService,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])


class CreateWithdrawalRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    requisites: str = Field(min_length=3, max_length=1000)


class CreateWalletTransferRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=160)


def _withdrawal_view(item: PartnerWithdrawal) -> dict[str, object]:
    return {
        "id": str(item.id),
        "amount": str(item.amount),
        "amount_rox": str(InternalCreditService.credits_for(item.amount)),
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "can_cancel": item.status == "pending",
    }


def _transfer_view(item: PartnerWalletTransfer) -> dict[str, object]:
    return {
        "id": str(item.id),
        "amount_rub": str(item.amount_rub),
        "rox_amount": str(item.rox_amount),
        "created_at": item.created_at.isoformat(),
    }


def _partner_chat_url() -> str | None:
    value = settings.partner_telegram_url.strip()
    return value if value.startswith("https://t.me/") else None


@router.get("/stats")
async def stats(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    first, second = await PartnerService.invitation_counts(session, user.id)
    accounting = await PartnerWalletTransferService.accounting(session, user.id)
    payload = f"ref_{user.telegram_id}"
    wallet = await session.get(Wallet, user.id)
    wallet_rox = Decimal(wallet.balance if wallet is not None else 0)
    withdrawable_rox = InternalCreditService.credits_for(accounting["available"])
    pending_rox = InternalCreditService.credits_for(accounting["pending_rewards"])
    partner_total_rox = InternalCreditService.credits_for(accounting["total_earned"])
    referral_link = PartnerService.referral_link(user.telegram_id)
    referral_mini_app_link = PartnerService.referral_mini_app_link(user.telegram_id)
    profile_link = PartnerService.profile_link(user.telegram_id)

    prompts_created = int(
        (
            await session.scalar(
                select(func.count()).select_from(Generation).where(
                    Generation.user_id == user.id,
                    Generation.source_feed_gen_id.is_(None),
                    Generation.prompt != "",
                )
            )
        )
        or 0
    )
    prompt_repeats = int(
        (
            await session.scalar(
                select(func.count()).select_from(FeedRemixEvent).where(
                    FeedRemixEvent.source_author_id == user.id,
                    FeedRemixEvent.remix_author_id != user.id,
                )
            )
        )
        or 0
    )
    latest_withdrawal = await session.scalar(
        select(PartnerWithdrawal)
        .where(PartnerWithdrawal.user_id == user.id)
        .order_by(PartnerWithdrawal.created_at.desc())
        .limit(1)
    )
    minimum_rub = max(Decimal("0"), settings.partner_min_withdrawal_rub)
    minimum_rox = InternalCreditService.credits_for(minimum_rub)

    return {
        "first_line": first,
        "second_line": second,
        "available": str(accounting["available"]),
        "partner_balance_rub": str(accounting["available"]),
        "pending": str(accounting["pending_rewards"]),
        "total_earned": str(accounting["total_earned"]),
        "transferred_to_rox": str(accounting["transferred_to_rox"]),
        "pending_withdrawals": str(accounting["pending_withdrawals"]),
        "minimum_withdrawal": str(minimum_rub),
        "first_line_percent": str(settings.referral_first_percent),
        "second_line_percent": str(settings.referral_second_percent),
        "referral_payload": payload,
        "referral_link": referral_link,
        "referral_bot_link": referral_link,
        "referral_mini_app_link": referral_mini_app_link,
        "profile_link": profile_link,
        "author_profile_link": profile_link,
        "partner_chat_url": _partner_chat_url(),
        "rox_balance": str(wallet_rox),
        "bonus_rox": str(wallet_rox),
        "withdrawable_rox": str(withdrawable_rox),
        "withdrawable_pending_rox": str(pending_rox),
        "partner_total_earned_rox": str(partner_total_rox),
        "total_rox": str(wallet_rox),
        "rub_per_rox": str(InternalCreditService.rub_per_credit()),
        "welcome_bonus_rox": str(settings.start_balance_rox),
        "invite_bonus_rox": str(settings.invite_bonus_rox),
        "prompt_repeat_bonus_rox": str(settings.prompt_repeat_bonus_rox),
        "minimum_withdrawal_rox": str(minimum_rox),
        "prompts_created": prompts_created,
        "prompt_repeats": prompt_repeats,
        "withdrawal_status": latest_withdrawal.status if latest_withdrawal is not None else "NONE",
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
                "amount_rox": str(InternalCreditService.credits_for(reward.amount)),
                "reversed_amount": str(Decimal(reversed_amount or 0)),
                "net_amount": str(
                    max(Decimal("0"), Decimal(reward.amount) - Decimal(reversed_amount or 0))
                ),
                "net_amount_rox": str(
                    InternalCreditService.credits_for(
                        max(Decimal("0"), Decimal(reward.amount) - Decimal(reversed_amount or 0))
                    )
                ),
                "status": reward.status,
                "created_at": reward.created_at.isoformat(),
            }
            for reward, source, reversed_amount in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/wallet-transfers")
async def wallet_transfers(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    rows = list(
        (
            await session.scalars(
                select(PartnerWalletTransfer)
                .where(PartnerWalletTransfer.user_id == user.id)
                .order_by(PartnerWalletTransfer.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return {"items": [_transfer_view(item) for item in rows], "limit": limit, "offset": offset}


@router.post("/wallet-transfers", status_code=201)
async def create_wallet_transfer(
    payload: CreateWalletTransferRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        item = await PartnerWalletTransferService.transfer(
            session,
            user_id=user.id,
            amount=payload.amount,
            idempotency_key=payload.idempotency_key,
        )
    except PartnerWalletTransferInsufficientFunds as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerWalletTransferError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _transfer_view(item)


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
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=160,
    ),
) -> dict[str, object]:
    try:
        item = await PartnerWalletTransferService.create_cash_withdrawal(
            session,
            user_id=user.id,
            amount=payload.amount,
            requisites=payload.requisites,
            idempotency_key=idempotency_key,
        )
    except PartnerWithdrawalIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerWalletTransferInsufficientFunds as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerInsufficientFunds as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerWithdrawalBelowMinimum as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (PartnerWithdrawalError, PartnerWalletTransferError) as exc:
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
