from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.models import Payment
from app.providers.payments import PaymentProviderError
from app.services.admin_security import AdminAuditService
from app.services.card_payments import CardPaymentService
from app.services.payment_refunds import PaymentRefundService
from app.services.payments import (
    PaymentIdempotencyConflict,
    PaymentService,
    UnsupportedPaymentOperation,
)

router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])

PaymentFinanceDep = Annotated[
    AdminContext,
    Depends(require_permission("users.wallet.adjust", step_up=True)),
]


class RefundPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    request_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=250)


@router.post("/{payment_id}/reconcile")
async def reconcile_payment(
    payment_id: uuid.UUID,
    request: Request,
    context: PaymentFinanceDep,
    session: SessionDep,
) -> dict[str, object]:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        if payment.provider == CardPaymentService.PROVIDER:
            updated = await CardPaymentService.reconcile(session, payment_id=payment.id)
        else:
            updated = await PaymentService.reconcile(session, payment_id=payment.id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await AdminAuditService.record(
        session,
        action="admin.payment.reconciled",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="payment",
        resource_id=str(payment.id),
        metadata={"provider": payment.provider, "status": updated.status},
    )
    await session.commit()
    return {
        "id": str(updated.id),
        "provider": updated.provider,
        "status": updated.status,
        "refunded_amount": str((updated.payload or {}).get("refunded_amount") or "0"),
        "refunded_credits": str((updated.payload or {}).get("refunded_credits") or "0"),
    }


@router.post("/{payment_id}/refund", status_code=202)
async def refund_payment(
    payment_id: uuid.UUID,
    payload: RefundPaymentRequest,
    request: Request,
    context: PaymentFinanceDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        refund = await PaymentRefundService.initiate(
            session,
            payment_id=payment_id,
            amount=payload.amount,
            request_key=str(payload.request_id),
            reason=payload.reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedPaymentOperation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (PaymentProviderError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await AdminAuditService.record(
        session,
        action="admin.payment.refund_requested",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="payment",
        resource_id=str(payment_id),
        reason=payload.reason,
        metadata={
            "provider": refund.provider,
            "amount": str(refund.amount),
            "currency": refund.currency,
            "refund_status": refund.status,
            "request_id": str(payload.request_id),
        },
    )
    await session.commit()
    payment = await session.get(Payment, payment_id)
    return {
        "payment_id": str(payment_id),
        "request_id": str(payload.request_id),
        "provider": refund.provider,
        "provider_refund_id": refund.provider_refund_id,
        "refund_status": refund.status,
        "payment_status": payment.status if payment else "unknown",
        "amount": str(refund.amount),
        "currency": refund.currency,
    }
