from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.services.partner_rox_transfer import (
    PartnerRoxRecipientNotAllowed,
    PartnerRoxTransferError,
    PartnerRoxTransferService,
)
from app.services.wallet import IdempotencyConflictError, InsufficientBalanceError

router = APIRouter(prefix="/referrals", tags=["referrals"])


class CreatePartnerRoxTransferRequest(BaseModel):
    # New customer contract: enter the numeric Telegram ID shown in ROXY profile.
    recipient_telegram_id: int | None = Field(default=None, gt=0)
    # Kept temporarily for already deployed clients during rollout.
    recipient_user_id: uuid.UUID | None = None
    amount_rox: int = Field(gt=0, le=1_000_000_000)
    idempotency_key: str = Field(min_length=8, max_length=96)


@router.post("/rox-transfers", status_code=201)
async def create_partner_rox_transfer(
    payload: CreatePartnerRoxTransferRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    if payload.recipient_telegram_id is None and payload.recipient_user_id is None:
        raise HTTPException(status_code=422, detail="Укажите ID пользователя")
    if payload.recipient_telegram_id is not None and payload.recipient_user_id is not None:
        raise HTTPException(status_code=422, detail="Укажите только один ID получателя")

    try:
        result = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=user.id,
            recipient_user_id=payload.recipient_user_id,
            recipient_telegram_id=payload.recipient_telegram_id,
            amount_rox=payload.amount_rox,
            idempotency_key=payload.idempotency_key,
        )
    except PartnerRoxRecipientNotAllowed as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Недостаточно ROX для перевода",
                "balance_rox": str(exc.current_balance),
                "required_rox": str(exc.required_amount),
            },
        ) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PartnerRoxTransferError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    return {
        "id": str(result.transfer_id),
        "recipient_user_id": str(result.recipient_user_id),
        "recipient_telegram_id": result.recipient_telegram_id,
        "amount_rox": str(payload.amount_rox),
        "balance_rox": str(result.sender_transaction.balance_after),
    }
