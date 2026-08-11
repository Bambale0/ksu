from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.services.promocodes import PromoCodeError, PromoCodeService

router = APIRouter(prefix="/promocodes", tags=["promocodes"])


class RedeemPromoRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.post("/redeem")
async def redeem(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    try:
        promo = await PromoCodeService.redeem(session, user_id=user.id, code=payload.code)
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "reward_rox": str(promo.reward_amount)}
