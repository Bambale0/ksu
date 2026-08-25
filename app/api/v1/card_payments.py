from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.models import Payment
from app.providers.payments import PaymentProviderError
from app.services.abuse_protection import AbuseProtectionService
from app.services.card_payments import CardPackageCatalog, CardPaymentService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payment_email import validate_billing_email
from app.services.payments import PaymentIdempotencyConflict, UnknownPaymentPackageError

router = APIRouter(prefix="/payments/card", tags=["payments"])


class CardCheckoutRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=64)
    currency: Literal["RUB", "USD", "EUR"]
    billing_email: str = Field(min_length=3, max_length=254)


def _view(payment: Payment, *, request_key: str | None = None) -> dict[str, str]:
    payload = payment.payload or {}
    bonus_credits = str(payload.get("bonus_credits") or "0")
    base_credits = str(payload.get("base_credits") or payment.rox_amount)
    return {
        "id": str(payment.id),
        "status": payment.status,
        "provider": CardPaymentService.PROVIDER,
        "label": CardPaymentService.PUBLIC_LABEL,
        "package_id": str(payload.get("package_id") or ""),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "credits": str(payment.rox_amount),
        "base_credits": base_credits,
        "bonus_credits": bonus_credits,
        "payment_url": str(payload.get("payment_url") or ""),
        "idempotency_key": request_key or str(payload.get("request_key") or ""),
    }


@router.get("/packages")
async def packages() -> dict[str, object]:
    packages = await CardPackageCatalog.provider_packages()
    currencies = sorted(
        {
            currency
            for package in packages.values()
            for currency in package.prices
        }
    )
    return {
        "provider": CardPaymentService.PROVIDER,
        "label": CardPaymentService.PUBLIC_LABEL,
        "currencies": currencies,
        "packages": {
            package_id: {
                "credits": str(package.credits),
                "bonus_credits": str(TopUpBonusService.bonus_for(package.credits)),
                "total_credits": str(TopUpBonusService.total_for(package.credits)),
                "prices": {
                    currency: str(amount)
                    for currency, amount in sorted(package.prices.items())
                },
            }
            for package_id, package in packages.items()
        },
    }


@router.post("/checkout", status_code=201)
async def checkout(
    payload: CardCheckoutRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        request_key = str(uuid.UUID(idempotency_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be a UUID") from exc
    try:
        billing_email = validate_billing_email(payload.billing_email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await AbuseProtectionService.payment_rate(redis, user.id)
    try:
        payment = await CardPaymentService.create(
            session,
            user_id=user.id,
            package_id=payload.package_id,
            currency=payload.currency,
            billing_email=billing_email,
            request_key=request_key,
        )
    except UnknownPaymentPackageError as exc:
        raise HTTPException(
            status_code=404,
            detail="Этот пакет недоступен в выбранной валюте",
        ) from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PaymentProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось открыть оплату картой. Попробуйте ещё раз позже.",
        ) from exc
    return _view(payment, request_key=request_key)


@router.get("/{payment_id}")
async def get_card_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id or payment.provider != CardPaymentService.PROVIDER:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _view(payment)


@router.post("/{payment_id}/reconcile")
async def reconcile_card_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id or payment.provider != CardPaymentService.PROVIDER:
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        payment = await CardPaymentService.reconcile(session, payment_id=payment.id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail="Не удалось обновить статус оплаты") from exc
    return _view(payment)
