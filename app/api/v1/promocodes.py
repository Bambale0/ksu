from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.services.card_payments import CardPackageCatalog
from app.services.payments import PaymentService
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
    "minimum_package_required": "Промокод даёт +50 ROX только на пакеты от 1000 ROX",
}


def _package_credits(package_id: str | None) -> Decimal | None:
    if not package_id:
        return None
    package = PaymentService.packages().get(package_id)
    if package is not None:
        return Decimal(package.credits)
    card_package = CardPackageCatalog.packages().get(package_id)
    if card_package is not None:
        return Decimal(card_package.credits)
    return None


async def _validate(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    requested_package_credits = _package_credits(payload.package_id)
    try:
        promo = await PromoCodeService.preview(
            session,
            user_id=user.id,
            code=payload.code,
            package_id=payload.package_id,
            base_credits=requested_package_credits,
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
    bound_package_credits = _package_credits(promo.package_id)
    return {
        "status": "valid",
        "code": promo.code,
        "reward_rox": str(promo.reward_amount),
        "package_id": promo.package_id,
        "package_credits": str(bound_package_credits) if bound_package_credits is not None else None,
        "min_package_credits": str(PromoCodeService.MIN_PROMO_BASE_CREDITS),
        "remaining_uses": remaining_uses,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "message": (
            f"Промокод добавит +{promo.reward_amount} ROX сверх подарка пакета "
            f"при оплате от {PromoCodeService.MIN_PROMO_BASE_CREDITS} ROX"
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
