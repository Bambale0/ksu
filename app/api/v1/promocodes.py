from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Wallet
from app.services.promocodes import PromoCodeError, PromoCodeService

router = APIRouter(prefix="/promocodes", tags=["promocodes"])


class RedeemPromoRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


PROMO_ERROR_MESSAGES = {
    "invalid": "Промокод не существует или недоступен",
    "expired": "Срок действия промокода истёк",
    "usage_limit_reached": "Лимит активаций промокода исчерпан",
    "already_attributed": "Партнёр уже закреплён за этим аккаунтом",
    "partner_unassigned": "Промокод пока не привязан к партнёру",
    "partner_unavailable": "Партнёр по этому промокоду сейчас недоступен",
    "program_inactive": "Партнёрская бонусная программа временно отключена",
    "self_ref": "Нельзя активировать собственный партнёрский промокод",
    "invalid_user": "Аккаунт недоступен для активации промокода",
    "referral_hourly_limit": "Лимит партнёрских активаций за час исчерпан",
    "referral_daily_limit": "Лимит партнёрских активаций за сутки исчерпан",
    "referral_burst_limit": "Слишком много активаций подряд. Попробуйте позже",
    "referral_burst_autoban": "Партнёрская программа для этого партнёра временно недоступна",
    "referral_blocked_referrer": "Партнёр по этому промокоду сейчас недоступен",
}


def _promo_error(exc: PromoCodeError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": exc.code,
            "message": PROMO_ERROR_MESSAGES.get(exc.code, "Не удалось применить промокод"),
        },
    )


async def _view(
    *,
    session: SessionDep,
    user: CurrentUserDep,
    code: str,
) -> dict[str, object]:
    promo = await PromoCodeService.preview(session, user_id=user.id, code=code)
    config = await PromoCodeService.program_config(session)
    relation = await PromoCodeService.relation_for_user(session, user_id=user.id)
    already_active = bool(
        relation is not None
        and relation.source == "promo"
        and relation.inviter_user_id == promo.partner_user_id
    )
    remaining_uses = await PromoCodeService.remaining_uses(session, promo=promo)
    return {
        "status": "valid",
        "code": promo.code,
        "partner_user_id": str(promo.partner_user_id),
        "welcome_rox": str(config.welcome_rox),
        # Backward-compatible alias for older Mini App clients.
        "reward_rox": str(config.welcome_rox),
        "first_line_percent": str(config.first_line_percent),
        "topup_partner_rox": str(config.topup_partner_rox),
        "topup_user_rox": str(config.topup_user_rox),
        "topup_user_min_rub": str(config.topup_user_min_rub),
        "already_active": already_active,
        "remaining_uses": remaining_uses,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "message": (
            "Партнёрская программа уже активна"
            if already_active
            else "Промокод готов к активации"
        ),
    }


@router.get("/active")
async def active_promo(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    return await PromoCodeService.active_state(session, user_id=user.id)


@router.post("/validate")
async def validate(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        return await _view(session=session, user=user, code=payload.code)
    except PromoCodeError as exc:
        raise _promo_error(exc) from exc


@router.post("/redeem")
async def redeem(
    payload: RedeemPromoRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        activation = await PromoCodeService.activate(
            session,
            user_id=user.id,
            code=payload.code,
        )
        await session.commit()
    except PromoCodeError as exc:
        if exc.preserve_transaction:
            await session.commit()
        else:
            await session.rollback()
        raise _promo_error(exc) from exc

    wallet = await session.get(Wallet, user.id)
    return {
        "status": "activated" if activation.activated else "already_active",
        "code": activation.promo.code,
        "partner_user_id": str(activation.promo.partner_user_id),
        "welcome_rox": str(activation.config.welcome_rox),
        "reward_rox": str(activation.config.welcome_rox),
        "first_line_percent": str(activation.config.first_line_percent),
        "topup_partner_rox": str(activation.config.topup_partner_rox),
        "topup_user_rox": str(activation.config.topup_user_rox),
        "topup_user_min_rub": str(activation.config.topup_user_min_rub),
        "balance_rox": str(wallet.balance if wallet is not None else 0),
        "message": (
            "Промокод активирован"
            if activation.activated
            else "Партнёрская программа уже активна"
        ),
    }
