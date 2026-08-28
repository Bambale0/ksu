from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx


class PaymentProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class CreatedPayment:
    external_id: str
    payment_url: str
    raw: dict[str, Any]


def _money(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _cryptopay_invoice_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    result = body.get("result") or []
    if isinstance(result, dict):
        result = result.get("items") or result.get("invoices") or []
    if not isinstance(result, list):
        return []
    return [dict(item) for item in result if isinstance(item, dict)]


class CryptoPayClient:
    def __init__(self, token: str, base_url: str = "https://pay.crypt.bot") -> None:
        if not token:
            raise PaymentProviderError("CRYPTOPAY_API_TOKEN is not configured")
        self.token = token
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"Crypto-Pay-API-Token": token},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_payment(
        self,
        *,
        local_id: str,
        amount: Decimal,
        currency: str,
        description: str,
    ) -> CreatedPayment:
        response = await self._client.post(
            "/api/createInvoice",
            json={
                "currency_type": "fiat",
                "fiat": currency,
                "amount": _money(amount),
                "payload": local_id,
                "description": description[:1024],
                "expires_in": 3600,
            },
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise PaymentProviderError(f"Crypto Pay createInvoice failed: {body!r}")
        invoice = body.get("result") or {}
        external_id = invoice.get("invoice_id")
        payment_url = (
            invoice.get("mini_app_invoice_url")
            or invoice.get("bot_invoice_url")
            or invoice.get("web_app_invoice_url")
            or ""
        )
        if external_id is None or not payment_url:
            raise PaymentProviderError(f"Crypto Pay returned incomplete invoice: {body!r}")
        return CreatedPayment(str(external_id), str(payment_url), body)

    async def get_invoice(self, external_id: str) -> dict[str, Any] | None:
        response = await self._client.get(
            "/api/getInvoices",
            params={"invoice_ids": external_id, "count": 1},
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise PaymentProviderError(f"Crypto Pay getInvoices failed: {body!r}")
        rows = _cryptopay_invoice_rows(body)
        return dict(rows[0]) if rows else None

    async def find_invoice_by_payload(self, local_id: str) -> dict[str, Any] | None:
        # Crypto Pay exposes no createInvoice idempotency key and no payload filter.
        # Scanning the latest invoice window is a recovery path for a lost create response.
        response = await self._client.get("/api/getInvoices", params={"count": 1000, "offset": 0})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise PaymentProviderError(f"Crypto Pay getInvoices failed: {body!r}")
        for item in _cryptopay_invoice_rows(body):
            if str(item.get("payload") or "") == local_id:
                return dict(item)
        return None

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        secret = hashlib.sha256(self.token.encode()).digest()
        expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class TBankClient:
    def __init__(
        self,
        terminal_key: str,
        password: str,
        base_url: str = "https://securepay.tinkoff.ru",
    ) -> None:
        if not terminal_key or not password:
            raise PaymentProviderError("T-Bank terminal credentials are not configured")
        self.terminal_key = terminal_key
        self.password = password
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(20.0, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _signed_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request_body = {"TerminalKey": self.terminal_key, **body}
        request_body["Token"] = make_tbank_token(request_body, self.password)
        response = await self._client.post(path, json=request_body)
        response.raise_for_status()
        payload = response.json()
        if payload.get("Success") is False:
            raise PaymentProviderError(f"T-Bank {path} failed: {payload!r}")
        return dict(payload)

    async def create_payment(
        self,
        *,
        local_id: str,
        amount: Decimal,
        description: str,
        notification_url: str,
        return_url: str,
    ) -> CreatedPayment:
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        request_body: dict[str, Any] = {
            "Amount": cents,
            "OrderId": local_id,
            "Description": description[:140],
            "PayType": "O",
        }
        if notification_url:
            request_body["NotificationURL"] = notification_url
        if return_url:
            request_body["SuccessURL"] = return_url
            request_body["FailURL"] = return_url
        body = await self._signed_post("/v2/Init", request_body)
        external_id = body.get("PaymentId")
        payment_url = body.get("PaymentURL")
        if external_id is None or not payment_url:
            raise PaymentProviderError(f"T-Bank returned incomplete payment: {body!r}")
        return CreatedPayment(str(external_id), str(payment_url), body)

    async def get_state(self, external_id: str) -> dict[str, Any]:
        return await self._signed_post("/v2/GetState", {"PaymentId": external_id})

    async def check_order(self, local_id: str) -> dict[str, Any]:
        return await self._signed_post("/v2/CheckOrder", {"OrderId": local_id})

    async def refund_full(self, *, external_id: str, request_key: str) -> dict[str, Any]:
        # /v2/Cancel without Amount performs a full refund for CONFIRMED payments.
        return await self._signed_post(
            "/v2/Cancel",
            {"PaymentId": external_id, "ExternalRequestId": request_key},
        )

    def verify_notification(self, payload: dict[str, Any]) -> bool:
        supplied = str(payload.get("Token") or "")
        if not supplied:
            return False
        expected = make_tbank_token(payload, self.password)
        return hmac.compare_digest(expected.lower(), supplied.lower())


def make_tbank_token(payload: dict[str, Any], password: str) -> str:
    values: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "Token" or value is None or isinstance(value, (dict, list)):
            continue
        values[key] = value
    values["Password"] = password
    source = "".join(_tbank_value(values[key]) for key in sorted(values))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _tbank_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class YooKassaClient:
    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        base_url: str = "https://api.yookassa.ru",
    ) -> None:
        if not shop_id or not secret_key:
            raise PaymentProviderError("YooKassa credentials are not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=httpx.BasicAuth(shop_id, secret_key),
            timeout=httpx.Timeout(20.0, connect=10.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_payment(
        self,
        *,
        local_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
    ) -> CreatedPayment:
        confirmation: dict[str, Any] = {"type": "redirect"}
        if return_url:
            confirmation["return_url"] = return_url
        response = await self._client.post(
            "/v3/payments",
            headers={"Idempotence-Key": local_id},
            json={
                "amount": {"value": _money(amount), "currency": currency},
                "capture": True,
                "confirmation": confirmation,
                "description": description[:128],
                "metadata": {"payment_id": local_id},
            },
        )
        response.raise_for_status()
        body = response.json()
        external_id = body.get("id")
        payment_url = (body.get("confirmation") or {}).get("confirmation_url")
        if not external_id or not payment_url:
            raise PaymentProviderError(f"YooKassa returned incomplete payment: {body!r}")
        return CreatedPayment(str(external_id), str(payment_url), body)

    async def get_payment(self, external_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v3/payments/{external_id}")
        response.raise_for_status()
        return response.json()

    async def create_refund(
        self,
        *,
        external_payment_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        description: str,
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/v3/refunds",
            headers={"Idempotence-Key": idempotency_key},
            json={
                "payment_id": external_payment_id,
                "amount": {"value": _money(amount), "currency": currency},
                "description": description[:250],
            },
        )
        response.raise_for_status()
        return response.json()
