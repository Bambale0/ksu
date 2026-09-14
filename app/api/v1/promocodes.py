from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.services.promocodes import PromoCodeError, PromoCodeService

router = APIRouter(prefix="/promocodes", tags=["promocodes"])


class RedeemPromoRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    package_id: str | None = Field(default=None, max_length=64)


PROMO_ERROR_MESSAGES = {
    "invalid": "Промокод не существует или недоступен",
    "expired": "Срок действия промокода истёк",
    "usage_limit_reached": "Лимит активаций промокода исчерпан",
    "already_used": "Вы уже использовали этот промокод",
    "already_reserved": "Этот промокод уже привязан к другой незавершённой оплате",
    "package_mismatch": "Этот промокод действует для другого пакета",
}


async def _validate(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        promo = await PromoCodeService.preview(
            session,
            user_id=user.id,
            code=payload.code,
            package_id=payload.package_id,
        )
    except PromoCodeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": PROMO_ERROR_MESSAGES.get(exc.code, "Не удалось проверить промокод"),
            },
        ) from exc

    remaining_uses = await PromoCodeService.remaining_uses(session, promo=promo)
    return {
        "status": "valid",
        "code": promo.code,
        "reward_rox": str(promo.reward_amount),
        "package_id": promo.package_id,
        "remaining_uses": remaining_uses,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "message": (
            f"После успешной оплаты начислим +{promo.reward_amount} ROX"
            + (f" для пакета {promo.package_id}" if promo.package_id else "")
        ),
    }


@router.post("/validate")
async def validate(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    return await _validate(payload, user, session)


@router.post("/redeem")
async def redeem(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    """Backward-compatible endpoint: promo codes no longer grant free ROX."""
    return await _validate(payload, user, session)
