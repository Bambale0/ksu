from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Payment
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError
from app.services.card_payment_recovery import CardPaymentRecoveryService
from app.services.card_payments import CardPaymentService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/payments/card", include_in_schema=False)
async def card_payment_webhook(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> dict[str, bool]:
    verifier = CardCheckoutClient("", settings.card_api_base_url, settings.card_webhook_key)
    try:
        if not verifier.verify_webhook_key(x_api_key):
            raise HTTPException(status_code=403, detail="Invalid card webhook key")
    finally:
        await verifier.aclose()

    payload: Any = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    event_type = str(payload.get("eventType") or payload.get("event_type") or "").strip().lower()
    if event_type not in {"payment.success", "payment.failed"}:
        return {"ok": True}
    contract_id = str(payload.get("contractId") or payload.get("contract_id") or "").strip()
    if not contract_id:
        raise HTTPException(status_code=400, detail="Missing payment contract id")

    async with SessionFactory() as session:
        payment = await session.scalar(
            select(Payment).where(
                Payment.provider == CardPaymentService.PROVIDER,
                Payment.external_id == contract_id,
            )
        )
        if payment is None:
            try:
                payment = await CardPaymentRecoveryService.recover_missing_external_id(
                    session,
                    external_id=contract_id,
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="Payment not found") from exc
            except PaymentProviderError as exc:
                # Keep the webhook retryable when provider lookup is unavailable or
                # more than one local unknown intent could match this contract.
                raise HTTPException(
                    status_code=502,
                    detail="Payment recovery failed",
                ) from exc
        try:
            await CardPaymentService.reconcile(
                session,
                payment_id=payment.id,
                event_type=event_type,
            )
        except PaymentProviderError as exc:
            # Non-2xx makes the provider retry its webhook. Do not acknowledge a
            # mismatched amount/currency or unavailable authoritative invoice state.
            raise HTTPException(status_code=502, detail="Payment reconciliation failed") from exc
    return {"ok": True}
