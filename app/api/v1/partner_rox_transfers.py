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
    recipient_user_id: uuid.UUID
    amount_rox: int = Field(gt=0, le=1_000_000_000)
    idempotency_key: str = Field(min_length=8, max_length=96)


@router.post("/rox-transfers", status_code=201)
async def create_partner_rox_transfer(
    payload: CreatePartnerRoxTransferRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        result = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=user.id,
            recipient_user_id=payload.recipient_user_id,
            amount_rox=payload.amount_rox,
            idempotency_key=payload.idempotency_key,
        )
    except PartnerRoxRecipientNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
        "recipient_user_id": str(payload.recipient_user_id),
        "amount_rox": str(payload.amount_rox),
        "balance_rox": str(result.sender_transaction.balance_after),
    }
