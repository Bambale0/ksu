from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, SessionDep
from app.services.partner_approval import PartnerApprovalError, PartnerApprovalService

router = APIRouter(prefix="/partner-approval", tags=["partner-approval"])


class PartnerApplyRequest(BaseModel):
    accepted: bool


@router.get("")
async def partner_status(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    application = await PartnerApprovalService.get(session, user_id=user.id)
    return PartnerApprovalService.public_view(application)


@router.post("")
async def partner_apply(
    payload: PartnerApplyRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        application, replayed = await PartnerApprovalService.submit(
            session,
            user_id=user.id,
            accepted=payload.accepted,
        )
        await session.commit()
        return {**PartnerApprovalService.public_view(application), "replayed": replayed}
    except PartnerApprovalError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
