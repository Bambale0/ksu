from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.providers.payments import PaymentProviderError
from app.services.credits import InternalCreditService
from app.services.payments import (
    PaymentService,
    UnknownPaymentPackageError,
    UnknownPaymentProviderError,
)

router = APIRouter(prefix="/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    provider: Literal["cryptobot", "tbank", "yookassa"]
    package_id: str = Field(min_length=1, max_length=64)


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
) -> dict[str, str]:
    try:
        payment = await PaymentService.create(
            session,
            user_id=user.id,
            provider=payload.provider,
            package_id=payload.package_id,
        )
    except UnknownPaymentPackageError as exc:
        raise HTTPException(status_code=404, detail="Unknown internal credit package") from exc
    except UnknownPaymentProviderError as exc:
        raise HTTPException(status_code=400, detail="Unsupported payment provider") from exc
    except (PaymentProviderError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

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
    }
