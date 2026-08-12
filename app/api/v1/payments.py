import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.models import Payment
from app.providers.payments import PaymentProviderError
from app.services.abuse_protection import AbuseProtectionService
from app.services.credits import InternalCreditService
from app.services.payments import (
    PaymentIdempotencyConflict,
    PaymentService,
    UnknownPaymentPackageError,
    UnknownPaymentProviderError,
)

router = APIRouter(prefix="/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    provider: Literal["cryptobot", "tbank", "yookassa"]
    package_id: str = Field(min_length=1, max_length=64)


def _payment_view(payment: Payment, *, request_key: str | None = None) -> dict[str, str]:
    return {
        "id": str(payment.id),
        "status": payment.status,
        "provider": payment.provider,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "credits": str(payment.rox_amount),
        "rox": str(payment.rox_amount),
        "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
        "payment_url": str(payment.payload.get("payment_url") or ""),
        "idempotency_key": request_key or str(payment.payload.get("request_key") or ""),
    }


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


@router.post("", status_code=201)
async def create_payment(
    payload: CreatePaymentRequest,
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

    await AbuseProtectionService.payment_rate(redis, user.id)

    try:
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
