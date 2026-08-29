from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from app.providers.payments import CreatedPayment, PaymentProviderError


SUCCESS_STATUSES = frozenset({"paid", "overpaid"})
PENDING_STATUSES = frozenset({"pending", "check", "awaiting_confirmation", "underpaid_check"})
FINAL_FAILURE_STATUSES = frozenset({"underpaid", "cancel", "aml_lock"})


def _money(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def make_2328_signature(payload: dict[str, Any], api_key: str) -> str:
    body = _compact_json(payload)
    encoded = base64.b64encode(body.encode("utf-8"))
    return hmac.new(api_key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def verify_2328_webhook(payload: dict[str, Any], api_key: str) -> bool:
    if not api_key:
        return False
    received = str(payload.get("sign") or "")
    if not received:
        return False
    unsigned = dict(payload)
    unsigned.pop("sign", None)
    expected = make_2328_signature(unsigned, api_key)
    return hmac.compare_digest(expected, received)


class Payment2328Client:
    def __init__(
        self,
        project_uuid: str,
        api_key: str,
        base_url: str = "https://api.2328.io/api",
    ) -> None:
        if not project_uuid or not api_key:
            raise PaymentProviderError("2328.io project UUID/API key are not configured")
        self.project_uuid = project_uuid
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": "ROXY/1.0"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = _compact_json(payload)
        signature = make_2328_signature(payload, self.api_key)
        try:
            response = await self._client.post(
                path,
                content=body.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "project": self.project_uuid,
                    "sign": signature,
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            text = exc.response.text[:1000].replace("\n", " ")
            raise PaymentProviderError(
                f"2328.io {path} failed: HTTP {exc.response.status_code}: {text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"2328.io {path} transport failed") from exc
        except ValueError as exc:
            raise PaymentProviderError(f"2328.io {path} returned invalid JSON") from exc

        if not isinstance(data, dict) or data.get("state") != 0:
            raise PaymentProviderError(f"2328.io {path} failed: {data!r}")
        result = data.get("result")
        if not isinstance(result, dict):
            raise PaymentProviderError(f"2328.io {path} returned no result object")
        return dict(result)

    async def create_payment(
        self,
        *,
        local_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        callback_url: str,
    ) -> CreatedPayment:
        if not callback_url:
            raise PaymentProviderError("2328.io requires a public callback URL")
        payload: dict[str, Any] = {
            "amount": _money(amount),
            "currency": currency.upper(),
            "order_id": local_id,
            "url_callback": callback_url,
            "description": description[:200],
            "ttl_seconds": 3600,
        }

        result = await self._post("/v1/payment", payload)
        external_id = str(result.get("uuid") or "")
        payment_url = str(result.get("url") or "")
        if not external_id or not payment_url:
            raise PaymentProviderError(f"2328.io returned incomplete payment: {result!r}")
        if str(result.get("order_id") or "") != local_id:
            raise PaymentProviderError("2328.io returned a mismatched order_id")
        return CreatedPayment(external_id=external_id, payment_url=payment_url, raw=result)

    async def get_payment_info(
        self,
        *,
        external_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not external_id and not order_id:
            raise ValueError("external_id or order_id is required")
        payload: dict[str, Any] = {}
        if external_id:
            payload["uuid"] = external_id
        if order_id:
            payload["order_id"] = order_id
        try:
            return await self._post("/v1/payment/info", payload)
        except PaymentProviderError as exc:
            # A not-yet-visible order after an ambiguous create is recoverable. Other
            # transport/provider failures stay explicit so the reconciler retries later.
            if "HTTP 404" in str(exc):
                return None
            raise
