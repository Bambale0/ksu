from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Wallet
from app.services.notifications import NotificationService
from app.services.promocodes import PromoCodeError, PromoCodeService

router = APIRouter(prefix="/promocodes", tags=["promocodes"])


class RedeemPromoRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


PROMO_ERROR_MESSAGES = {
    "invalid": "Промокод не существует или недоступен",
    "expired": "Срок действия промокода истёк",
    "usage_limit_reached": "Лимит активаций промокода исчерпан",
    "already_used": "Вы уже использовали этот промокод",
}


@router.post("/redeem")
async def redeem(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    try:
        promo = await PromoCodeService.redeem(session, user_id=user.id, code=payload.code)
        wallet = await session.get(Wallet, user.id)
        await NotificationService.create(
            session,
            user_id=user.id,
            kind="promo_redeemed",
            title="Промокод применён",
            body=f"Начислено {promo.reward_amount} кредитов.",
        )
        await session.commit()
    except PromoCodeError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": PROMO_ERROR_MESSAGES.get(exc.code, "Не удалось применить промокод"),
            },
        ) from exc
    return {
        "status": "ok",
        "reward_rox": str(promo.reward_amount),
        "balance_rox": str(wallet.balance if wallet else promo.reward_amount),
    }
