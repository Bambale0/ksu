import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.core.config import settings
from app.db.models import Payment
from app.providers.payments import PaymentProviderError
from app.services.abuse_protection import AbuseProtectionService
from app.services.card_payments import CardPackage
from app.services.credits import InternalCreditService
from app.services.crypto_payments import CryptoBotPaymentService
from app.services.payment_2328 import Payment2328Service
from app.services.payment_bonuses import TopUpBonusService
from app.services.payments import (
    PaymentIdempotencyConflict,
    PaymentPackage,
    PaymentService,
    UnknownPaymentPackageError,
    UnknownPaymentProviderError,
)
from app.services.yookassa_payments import YooKassaPaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    provider: Literal["cryptobot", "2328", "tbank", "yookassa"]
    package_id: str = Field(min_length=1, max_length=64)


class CryptoCheckoutRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=64)


def _payment_label(payment: Payment) -> str:
    if payment.provider == CryptoBotPaymentService.PROVIDER:
        return CryptoBotPaymentService.PUBLIC_LABEL
    if payment.provider == Payment2328Service.PROVIDER:
        return "2328"
    if payment.provider == "yookassa":
        return "ЮKassa"
    return payment.provider


def _payment_view(payment: Payment, *, request_key: str | None = None) -> dict[str, str]:
    payload = payment.payload or {}
    return {
        "id": str(payment.id),
        "status": payment.status,
        "provider": payment.provider,
        "label": _payment_label(payment),
        "package_id": str(payload.get("package_id") or ""),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "credits": str(payment.rox_amount),
        "rox": str(payment.rox_amount),
        "base_credits": str(payload.get("base_credits") or payment.rox_amount),
        "bonus_credits": str(payload.get("bonus_credits") or "0"),
        "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
        "payment_url": str(payload.get("payment_url") or ""),
        "idempotency_key": request_key or str(payload.get("request_key") or ""),
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
    }


def _catalog_package(package: CardPackage, *, currency: str) -> dict[str, object]:
    credits = package.credits
    return {
        "credits": str(credits),
        "bonus_credits": str(TopUpBonusService.bonus_for(credits)),
        "total_credits": str(TopUpBonusService.total_for(credits)),
        "prices": {currency: str(package.prices[currency])},
    }


def _yookassa_catalog_package(package: PaymentPackage) -> dict[str, object]:
    credits = package.credits
    return {
        "credits": str(credits),
        "bonus_credits": str(TopUpBonusService.bonus_for(credits)),
        "total_credits": str(TopUpBonusService.total_for(credits)),
        "prices": {package.currency: str(package.amount)},
    }


def _yookassa_configured() -> bool:
    return YooKassaPaymentService.provider_configured("yookassa") and bool(
        settings.payment_return_url or settings.public_base_url
    )


@router.get("/packages")
async def list_packages() -> dict[str, object]:
    return {
        "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
        "packages": {
            package_id: {
                "amount": str(package.amount),
                "currency": package.currency,
                "credits": str(package.credits),
                "rox": str(package.rox_amount),
            }
            for package_id, package in PaymentService.packages().items()
        },
    }


@router.get("/yookassa/packages")
async def list_yookassa_packages() -> dict[str, object]:
    packages = PaymentService.packages()
    return {
        "provider": "yookassa",
        "label": "ЮKassa",
        "configured": _yookassa_configured(),
        "currencies": ["RUB"],
        "packages": {
            package_id: _yookassa_catalog_package(package)
            for package_id, package in packages.items()
        },
    }


@router.get("/crypto/packages")
async def list_crypto_packages() -> dict[str, object]:
    """Primary cryptocurrency checkout catalog: CryptoBot."""
    packages = await CryptoBotPaymentService.provider_packages()
    return {
        "provider": CryptoBotPaymentService.PROVIDER,
        "label": CryptoBotPaymentService.PUBLIC_LABEL,
        "configured": CryptoBotPaymentService.provider_configured(),
        "currencies": [CryptoBotPaymentService.CURRENCY],
        "packages": {
            package_id: _catalog_package(package, currency=CryptoBotPaymentService.CURRENCY)
            for package_id, package in packages.items()
        },
    }


@router.get("/crypto/2328/packages")
async def list_2328_crypto_packages() -> dict[str, object]:
    packages = await Payment2328Service.provider_packages()
    return {
        "provider": Payment2328Service.PROVIDER,
        "label": "2328",
        "configured": Payment2328Service.provider_configured(),
        "currencies": [Payment2328Service.CURRENCY],
        "packages": {
            package_id: _catalog_package(package, currency=Payment2328Service.CURRENCY)
            for package_id, package in packages.items()
        },
    }


@router.post("/crypto/checkout", status_code=201)
async def create_crypto_payment(
    payload: CryptoCheckoutRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """Primary cryptocurrency checkout: CryptoBot."""
    request_key = _validated_request_key(idempotency_key)
    await AbuseProtectionService.payment_rate(redis, user.id)
    try:
        payment = await CryptoBotPaymentService.create(
            session,
            user_id=user.id,
            package_id=payload.package_id,
            request_key=request_key,
        )
    except UnknownPaymentPackageError as exc:
        raise HTTPException(status_code=404, detail="Этот пакет недоступен в CryptoBot") from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PaymentProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось открыть CryptoBot. Попробуйте ещё раз позже.",
        ) from exc
    return _payment_view(payment, request_key=request_key)


@router.post("/crypto/2328/checkout", status_code=201)
async def create_2328_crypto_payment(
    payload: CryptoCheckoutRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    request_key = _validated_request_key(idempotency_key)
    await AbuseProtectionService.payment_rate(redis, user.id)
    try:
        payment = await Payment2328Service.create(
            session,
            user_id=user.id,
            package_id=payload.package_id,
            request_key=request_key,
        )
    except UnknownPaymentPackageError as exc:
        raise HTTPException(status_code=404, detail="Этот пакет недоступен в 2328") from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PaymentProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось открыть оплату через 2328. Попробуйте ещё раз позже.",
        ) from exc
    return _payment_view(payment, request_key=request_key)


@router.post("/crypto/{payment_id}/reconcile")
async def reconcile_crypto_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if (
        payment is None
        or payment.user_id != user.id
        or payment.provider
        not in {CryptoBotPaymentService.PROVIDER, Payment2328Service.PROVIDER}
    ):
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        if payment.provider == Payment2328Service.PROVIDER:
            payment = await Payment2328Service.reconcile(session, payment_id=payment.id)
        else:
            payment = await PaymentService.reconcile(session, payment_id=payment.id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail="Не удалось обновить статус оплаты") from exc
    return _payment_view(payment)


@router.post("/crypto/2328/{payment_id}/reconcile")
async def reconcile_2328_crypto_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if (
        payment is None
        or payment.user_id != user.id
        or payment.provider != Payment2328Service.PROVIDER
    ):
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        payment = await Payment2328Service.reconcile(session, payment_id=payment.id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail="Не удалось обновить статус оплаты") from exc
    return _payment_view(payment)


@router.post("/yookassa/{payment_id}/reconcile")
async def reconcile_yookassa_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id or payment.provider != "yookassa":
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        payment = await PaymentService.reconcile(session, payment_id=payment.id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail="Не удалось обновить статус ЮKassa") from exc
    return _payment_view(payment)


def _validated_request_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    try:
        return str(uuid.UUID(idempotency_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be a UUID") from exc


@router.get("")
async def list_user_payments(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, object]:
    payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(Payment.user_id == user.id)
                .order_by(Payment.created_at.desc(), Payment.id.desc())
                .limit(limit)
            )
        ).all()
    )
    return {"items": [_payment_view(payment) for payment in payments]}


@router.post("", status_code=201)
async def create_payment(
    payload: CreatePaymentRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    request_key = _validated_request_key(idempotency_key)
    await AbuseProtectionService.payment_rate(redis, user.id)

    try:
        if payload.provider == CryptoBotPaymentService.PROVIDER:
            payment = await CryptoBotPaymentService.create(
                session,
                user_id=user.id,
                package_id=payload.package_id,
                request_key=request_key,
            )
        elif payload.provider == Payment2328Service.PROVIDER:
            payment = await Payment2328Service.create(
                session,
                user_id=user.id,
                package_id=payload.package_id,
                request_key=request_key,
            )
        elif payload.provider == YooKassaPaymentService.PROVIDER:
            payment = await YooKassaPaymentService.create(
                session,
                user_id=user.id,
                package_id=payload.package_id,
                request_key=request_key,
            )
        else:
            payment = await PaymentService.create(
                session,
                user_id=user.id,
                provider=payload.provider,
                package_id=payload.package_id,
                request_key=request_key,
            )
    except UnknownPaymentPackageError as exc:
        raise HTTPException(status_code=404, detail="Unknown internal credit package") from exc
    except UnknownPaymentProviderError as exc:
        raise HTTPException(status_code=400, detail="Unsupported payment provider") from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (PaymentProviderError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _payment_view(payment, request_key=request_key)


@router.get("/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _payment_view(payment)
