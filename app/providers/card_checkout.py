from __future__ import annotations

import hmac
from decimal import Decimal
from typing import Any

import httpx

from app.providers.payments import CreatedPayment, PaymentProviderError


class CardCheckoutClient:
    SUPPORTED_CURRENCIES = frozenset({"RUB", "USD", "EUR"})
    SUPPORTED_PAYMENT_PROVIDERS = {
        "RUB": frozenset({"BANK131"}),
        "USD": frozenset({"UNLIMINT", "PAYPAL", "STRIPE"}),
        "EUR": frozenset({"UNLIMINT", "PAYPAL", "STRIPE"}),
    }
    # Official custom-price limits for POST /api/v3/invoice.
    AMOUNT_LIMITS = {
        "RUB": (Decimal("50"), Decimal("1000000")),
        "USD": (Decimal("5"), Decimal("10000")),
        "EUR": (Decimal("5"), Decimal("10000")),
    }

    def __init__(self, api_key: str, base_url: str, webhook_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.webhook_key = webhook_key
        self._products_cache: dict[str, Any] | None = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise PaymentProviderError("Card checkout API key is not configured")
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    @classmethod
    def validate_route(cls, currency: str, payment_provider: str | None) -> None:
        currency = currency.upper()
        if currency not in cls.SUPPORTED_CURRENCIES:
            raise PaymentProviderError(f"Unsupported card checkout currency: {currency}")
        if payment_provider is None:
            return
        provider = payment_provider.upper()
        if provider not in cls.SUPPORTED_PAYMENT_PROVIDERS[currency]:
            raise PaymentProviderError(
                f"Payment route {provider} is not supported for {currency}"
            )

    @classmethod
    def validate_amount(cls, currency: str, amount: Decimal) -> None:
        currency = currency.upper()
        if currency not in cls.AMOUNT_LIMITS:
            raise PaymentProviderError(f"Unsupported card checkout currency: {currency}")
        minimum, maximum = cls.AMOUNT_LIMITS[currency]
        if amount < minimum or amount > maximum:
            raise PaymentProviderError(
                f"Card checkout amount for {currency} must be between {minimum} and {maximum}"
            )

    async def create_invoice(
        self,
        *,
        email: str,
        offer_id: str,
        currency: str,
        amount: Decimal | None,
        payment_provider: str | None = None,
    ) -> CreatedPayment:
        currency = currency.upper()
        self.validate_route(currency, payment_provider)
        if amount is not None:
            self.validate_amount(currency, amount)
        if not offer_id:
            raise PaymentProviderError("Card checkout offer id is not configured")

        # Lava's custom-price endpoint names this field offerId, but for products
        # published as "Price on request via API" it must contain the *content /
        # product id*, not a nested offer id. Older KSU resolver paths can still
        # hand us a nested id after inspecting /api/v2/products, so enforce the
        # upstream contract at the provider boundary before creating the invoice.
        invoice_offer_id = offer_id
        if amount is not None:
            invoice_offer_id = await self._normalize_dynamic_content_id(offer_id)

        payload: dict[str, Any] = {
            "email": email,
            "offerId": invoice_offer_id,
            "currency": currency,
        }
        if amount is not None:
            payload["amount"] = float(amount)
        if payment_provider:
            payload["paymentProvider"] = payment_provider.upper()
        try:
            response = await self._client.post(
                "/api/v3/invoice",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            raw = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:1000].replace("\n", " ")
            raise PaymentProviderError(
                f"Card checkout invoice creation failed: HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Card checkout transport failed") from exc
        except ValueError as exc:
            raise PaymentProviderError("Card checkout returned invalid JSON") from exc
        data = self._unwrap(raw)
        external_id = self.extract_invoice_id(data)
        payment_url = self.extract_payment_url(data)
        if not external_id or not payment_url:
            raise PaymentProviderError("Card checkout returned an incomplete invoice")
        return CreatedPayment(
            external_id=external_id,
            payment_url=payment_url,
            raw=raw,
        )

    async def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        if not invoice_id:
            raise PaymentProviderError("Card checkout invoice id is missing")
        try:
            # Current public Swagger exposes the single-contract lookup here.
            response = await self._client.get(
                f"/api/v1/invoices/{invoice_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            raw = response.json()
        except httpx.HTTPStatusError as exc:
            raise PaymentProviderError(
                f"Card checkout invoice lookup failed: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Card checkout transport failed") from exc
        except ValueError as exc:
            raise PaymentProviderError("Card checkout returned invalid JSON") from exc
        return self._unwrap(raw)

    async def get_products(self) -> dict[str, Any]:
        if self._products_cache is not None:
            return self._products_cache
        try:
            response = await self._client.get(
                "/api/v2/products",
                headers=self._headers(),
                params={"feedVisibility": "ALL"},
            )
            response.raise_for_status()
            raw = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:1000].replace("\n", " ")
            raise PaymentProviderError(
                f"Card checkout products lookup failed: HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Card checkout transport failed") from exc
        except ValueError as exc:
            raise PaymentProviderError("Card checkout returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise PaymentProviderError("Card checkout returned invalid products JSON")
        self._products_cache = raw
        return raw

    async def _normalize_dynamic_content_id(self, configured_id: str) -> str:
        try:
            payload = await self.get_products()
        except PaymentProviderError:
            # A configured content id is already the correct value for v3. If the
            # catalog is temporarily unavailable, do not block invoice creation.
            return configured_id

        for product in self._products_from_payload(payload):
            product_id = self._object_id(product, product_keys=True)
            if not product_id:
                continue
            if product_id == configured_id:
                return product_id
            for offer in self._offers_from_product(product):
                if self._object_id(offer, product_keys=False) == configured_id:
                    return product_id
        return configured_id

    @staticmethod
    def _products_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[Any] = [payload.get("items"), payload.get("products")]
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.extend([data.get("items"), data.get("products")])
        elif isinstance(data, list):
            candidates.append(data)
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    @staticmethod
    def _offers_from_product(product: dict[str, Any]) -> list[dict[str, Any]]:
        offers = product.get("offers")
        if isinstance(offers, list):
            return [offer for offer in offers if isinstance(offer, dict)]
        offer = product.get("offer")
        if isinstance(offer, dict):
            return [offer]
        return []

    @staticmethod
    def _object_id(item: dict[str, Any], *, product_keys: bool) -> str:
        keys = ("id", "productId", "product_id") if product_keys else (
            "id",
            "offerId",
            "offer_id",
        )
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def verify_webhook_key(self, supplied: str | None) -> bool:
        if not self.webhook_key or not supplied:
            return False
        return hmac.compare_digest(self.webhook_key, supplied)

    @staticmethod
    def _unwrap(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PaymentProviderError("Card checkout returned invalid JSON")
        for key in ("data", "invoice", "contract", "result", "payload"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload

    @staticmethod
    def extract_invoice_id(payload: dict[str, Any]) -> str:
        return str(
            payload.get("id")
            or payload.get("contractId")
            or payload.get("invoiceId")
            or payload.get("contract_id")
            or payload.get("invoice_id")
            or ""
        )

    @staticmethod
    def extract_payment_url(payload: dict[str, Any]) -> str:
        return str(
            payload.get("paymentUrl")
            or payload.get("paymentURL")
            or payload.get("payment_url")
            or payload.get("paymentLink")
            or payload.get("payment_link")
            or payload.get("checkoutUrl")
            or payload.get("checkout_url")
            or payload.get("redirectUrl")
            or payload.get("redirect_url")
            or payload.get("url")
            or payload.get("link")
            or ""
        )

    @staticmethod
    def extract_status(payload: dict[str, Any]) -> str:
        raw = (
            payload.get("status")
            or payload.get("paymentStatus")
            or payload.get("invoiceStatus")
            or payload.get("contractStatus")
            or ""
        )
        return str(raw).strip().lower()

    @staticmethod
    def extract_amount(payload: dict[str, Any]) -> Decimal | None:
        raw: Any = payload.get("amount")
        if isinstance(raw, dict):
            raw = raw.get("value") or raw.get("amount")
        if raw in (None, ""):
            return None
        try:
            return Decimal(str(raw))
        except Exception as exc:  # noqa: BLE001
            raise PaymentProviderError("Card checkout returned invalid invoice amount") from exc

    @staticmethod
    def extract_currency(payload: dict[str, Any]) -> str | None:
        raw: Any = payload.get("currency")
        if isinstance(raw, dict):
            raw = raw.get("code") or raw.get("currency")
        if raw in (None, ""):
            return None
        return str(raw).upper()

    @staticmethod
    def extract_buyer_email(payload: dict[str, Any]) -> str | None:
        buyer: Any = payload.get("buyer")
        if isinstance(buyer, dict):
            raw = buyer.get("email")
            if raw not in (None, ""):
                return str(raw).strip().lower()
        for key in ("buyerEmail", "buyer_email", "email"):
            raw = payload.get(key)
            if raw not in (None, ""):
                return str(raw).strip().lower()
        return None

    @staticmethod
    def extract_refunded_amount(payload: dict[str, Any]) -> Decimal | None:
        for key in ("refundedAmount", "refundAmount", "refunded_amount"):
            raw: Any = payload.get(key)
            if isinstance(raw, dict):
                raw = raw.get("value") or raw.get("amount")
            if raw not in (None, ""):
                try:
                    return Decimal(str(raw))
                except Exception as exc:  # noqa: BLE001
                    raise PaymentProviderError(
                        "Card checkout returned invalid refunded amount"
                    ) from exc
        return None
