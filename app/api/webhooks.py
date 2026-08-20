import hmac
import json
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_models import PaymentRefundRequest
from app.db.session import SessionFactory
from app.providers.kie import extract_kie_task_id, verify_kie_webhook
from app.providers.payments import CryptoPayClient, YooKassaClient, make_tbank_token
from app.services.generation_provider import GenerationProviderService
from app.services.payments import PaymentService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.telegram_webhook_secret and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update, redis=request.app.state.redis)
    return {"ok": True}


@router.post("/kie", include_in_schema=False)
async def kie_webhook(
    request: Request,
    x_webhook_timestamp: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
) -> dict[str, bool]:
    payload = await request.json()
    task_id = extract_kie_task_id(payload)
    if not task_id:
        raise HTTPException(status_code=400, detail="Missing Kie task id")
    query_token = request.query_params.get("token")
    token_valid = bool(
        settings.kie_webhook_hmac_key
        and query_token
        and hmac.compare_digest(query_token, settings.kie_webhook_hmac_key)
    )
    if not token_valid and not verify_kie_webhook(
        task_id=task_id,
        timestamp=x_webhook_timestamp,
        signature=x_webhook_signature,
        hmac_key=settings.kie_webhook_hmac_key,
    ):
        raise HTTPException(status_code=403, detail="Invalid Kie webhook signature")

    generation_id: uuid.UUID | None = None
    raw_generation_id = request.query_params.get("generation_id")
    if raw_generation_id:
        try:
            generation_id = uuid.UUID(raw_generation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid generation id") from exc

    async with SessionFactory() as session:
        await GenerationProviderService.sync_kie_task(
            session,
            task_id=task_id,
            generation_id=generation_id,
        )
    return {"ok": True}


@router.post("/payments/cryptobot", include_in_schema=False)
async def cryptobot_webhook(
    request: Request,
    crypto_pay_api_signature: str | None = Header(
        default=None,
        alias="crypto-pay-api-signature",
    ),
) -> dict[str, bool]:
    raw_body = await request.body()
    client = CryptoPayClient(settings.cryptopay_api_token, settings.cryptopay_base_url)
    try:
        if not client.verify_webhook(raw_body, crypto_pay_api_signature):
            raise HTTPException(status_code=403, detail="Invalid Crypto Pay signature")
    finally:
        await client.aclose()

    try:
        update = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if update.get("update_type") != "invoice_paid":
        return {"ok": True}

    invoice = update.get("payload") or {}
    payment_id = _uuid_or_400(invoice.get("payload"))
    async with SessionFactory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.provider != "cryptobot":
            raise HTTPException(status_code=404, detail="Payment not found")
        invoice_id = str(invoice.get("invoice_id") or "")
        if payment.external_id and invoice_id != str(payment.external_id):
            raise HTTPException(status_code=409, detail="Crypto Pay invoice mismatch")
        if not payment.external_id:
            payment.external_id = invoice_id
        PaymentService.assert_amount(
            payment,
            amount=Decimal(str(invoice.get("amount") or "0")),
            currency=str(invoice.get("fiat") or payment.currency),
        )
        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload=update,
        )
    return {"ok": True}


@router.post("/payments/tbank", include_in_schema=False, response_class=PlainTextResponse)
async def tbank_webhook(request: Request) -> PlainTextResponse:
    payload = await _json_or_form(request)
    if not settings.tbank_password or not settings.tbank_terminal_key:
        raise HTTPException(status_code=503, detail="T-Bank is not configured")
    supplied_token = str(payload.get("Token") or "")
    expected_token = make_tbank_token(payload, settings.tbank_password)
    if not supplied_token or not hmac.compare_digest(
        supplied_token.lower(),
        expected_token.lower(),
    ):
        raise HTTPException(status_code=403, detail="Invalid T-Bank token")
    if str(payload.get("TerminalKey") or "") != settings.tbank_terminal_key:
        raise HTTPException(status_code=403, detail="Invalid T-Bank terminal")

    async with SessionFactory() as session:
        payment: Payment | None = None
        raw_order_id = payload.get("OrderId")
        if raw_order_id:
            try:
                payment = await session.get(Payment, uuid.UUID(str(raw_order_id)))
            except ValueError:
                payment = None
        if payment is None and payload.get("PaymentId"):
            payment = await session.scalar(
                select(Payment).where(
                    Payment.provider == "tbank",
                    Payment.external_id == str(payload.get("PaymentId")),
                )
            )
        if payment is None or payment.provider != "tbank":
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.external_id and str(payload.get("PaymentId") or "") != str(payment.external_id):
            raise HTTPException(status_code=409, detail="T-Bank payment mismatch")

        state_payload = dict(payload)
        if str(payload.get("Status") or "").upper() in {
            "PARTIAL_REFUNDED",
            "PARTIAL_REVERSED",
        }:
            # Notification Amount can describe the refund operation rather than the
            # original payment. Signature validation already used the untouched body;
            # downstream accounting must not mistake this value for total payment size.
            state_payload.pop("Amount", None)
            state_payload["NotificationAmount"] = payload.get("Amount")
        await PaymentService.apply_tbank_state(session, payment.id, state_payload)
    return PlainTextResponse("OK", status_code=200)


@router.post("/payments/yookassa", include_in_schema=False)
async def yookassa_webhook(request: Request) -> dict[str, bool]:
    update = await request.json()
    event = str(update.get("event") or "")
    webhook_object = update.get("object") or {}

    refund_event_id: str | None = None
    if event == "refund.succeeded":
        provider_payment_id = str(webhook_object.get("payment_id") or "")
        refund_event_id = str(webhook_object.get("id") or "") or None
    elif event.startswith("payment."):
        provider_payment_id = str(webhook_object.get("id") or "")
    else:
        return {"ok": True}
    if not provider_payment_id:
        raise HTTPException(status_code=400, detail="Missing YooKassa payment id")

    client = YooKassaClient(
        settings.yookassa_shop_id,
        settings.yookassa_secret_key,
        settings.yookassa_base_url,
    )
    try:
        # The webhook body is only a signal. The authoritative payment object also
        # exposes cumulative refunded_amount, so partial/manual refunds reconcile safely.
        authoritative = await client.get_payment(provider_payment_id)
    finally:
        await client.aclose()

    metadata = authoritative.get("metadata") or {}
    payment_id = _uuid_or_400(metadata.get("payment_id"))
    async with SessionFactory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.provider != "yookassa":
            raise HTTPException(status_code=404, detail="Payment not found")
        if payment.external_id and str(payment.external_id) != provider_payment_id:
            raise HTTPException(status_code=409, detail="YooKassa payment mismatch")
        if not payment.external_id:
            payment.external_id = provider_payment_id
            await session.commit()

        await PaymentService.apply_yookassa_state(
            session,
            payment.id,
            authoritative,
            refund_event_id=refund_event_id,
        )

        if refund_event_id:
            refund_request = await session.scalar(
                select(PaymentRefundRequest).where(
                    PaymentRefundRequest.payment_id == payment.id,
                    PaymentRefundRequest.provider_refund_id == refund_event_id,
                )
            )
            if refund_request is not None:
                refund_request.status = "succeeded"
                refund_request.provider_payload = webhook_object
                refund_request.last_error = None
                await session.commit()
    return {"ok": True}


async def _json_or_form(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        return dict(payload)
    body = (await request.body()).decode("utf-8")
    return dict(parse_qsl(body, keep_blank_values=True))


def _uuid_or_400(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid local payment id") from exc
