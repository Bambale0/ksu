from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.core.payment_2328_config import payment_2328_settings
from app.db.models import Payment
from app.db.session import SessionFactory
from app.providers.payment_2328 import verify_2328_webhook
from app.services.payment_2328 import Payment2328Service

router = APIRouter(prefix="/webhooks/payments", tags=["webhooks"])


@router.post("/2328", include_in_schema=False)
async def payment_2328_webhook(request: Request) -> dict[str, bool]:
    if not Payment2328Service.provider_configured():
        raise HTTPException(status_code=503, detail="2328.io is not configured")
    try:
        payload: Any = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    if not verify_2328_webhook(payload, payment_2328_settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid 2328.io signature")

    order_id = str(payload.get("order_id") or "")
    if not order_id:
        raise HTTPException(status_code=400, detail="Missing order_id")

    try:
        payment_id = uuid.UUID(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid order_id") from exc

    async with SessionFactory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.provider != Payment2328Service.PROVIDER:
            raise HTTPException(status_code=404, detail="Payment not found")
        await Payment2328Service.apply_state(
            session,
            payment=payment,
            provider_payload=payload,
        )
    return {"ok": True}
