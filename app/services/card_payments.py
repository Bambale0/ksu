from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment, WalletTransaction
from app.db.payment_models import PaymentRequest
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError, PaymentProviderValidationError
from app.services.credits import InternalCreditService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payments import PaymentIdempotencyConflict, PaymentService, UnknownPaymentPackageError
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


@dataclass(frozen=True, slots=True)
class CardPackage:
    package_id: str
    credits: Decimal
    prices: dict[str, Decimal]
    offer_id: str | None = None
    # Lava rejects `amount` for fixed-price offers (HTTP 400 "is not dynamic
    # price"). Only explicitly dynamic/price-on-request packages may send it.
    dynamic_amount: bool = False


@dataclass(frozen=True, slots=True)
class CardOfferResolution:
    offer_id: str
    source: str


class CardPackageCatalog:
    CURRENCIES = frozenset({"RUB", "USD", "EUR"})
    DYNAMIC_PRICE_KEYS = frozenset(
        {
            "apiPrice",
            "customPrice",
            "dynamicPrice",
            "isCustomPrice",
            "isDynamicPrice",
            "isPriceOnRequest",
            "isPriceOnRequestViaApi",
            "isPriceOnRequestViaAPI",
            "priceByRequest",
            "priceOnRequest",
            "priceOnRequestViaApi",
            "priceOnRequestViaAPI",
            "price_on_request",
            "requestPrice",
        }
    )

    @classmethod
    def packages(cls) -> dict[str, CardPackage]:
        try:
            raw = json.loads(settings.card_packages_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("CARD_PACKAGES_JSON is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("CARD_PACKAGES_JSON must be a JSON object")
        if raw:
            return cls._parse_card_packages(raw)

        # Backward-compatible RUB-only package view. Foreign-currency prices are
        # never derived from RUB; operators must configure them explicitly.
        return {
            package_id: CardPackage(
                package_id=package_id,
                credits=package.credits,
                prices={"RUB": package.amount},
                offer_id=None,
            )
            for package_id, package in PaymentService.packages().items()
        }

    @classmethod
    def _parse_card_packages(cls, raw: dict[str, Any]) -> dict[str, CardPackage]:
        result: dict[str, CardPackage] = {}
        for package_id, item in raw.items():
            if not isinstance(item, dict):
                continue
            credits_raw = item.get("credits", item.get("rox"))
            prices_raw = item.get("prices")
            if credits_raw is None or not isinstance(prices_raw, dict):
                continue
            credits = Decimal(str(credits_raw))
            if credits <= 0:
                continue
            prices: dict[str, Decimal] = {}
            for currency, value in prices_raw.items():
                code = str(currency).upper()
                if code not in cls.CURRENCIES:
                    raise ValueError(f"Unsupported card package currency: {code}")
                amount = Decimal(str(value))
                if amount <= 0:
                    raise ValueError(f"Card package {package_id} price must be positive")
                prices[code] = amount
            if not prices:
                continue
            offer_id = str(item.get("offer_id") or "").strip() or None
            dynamic_amount = cls._coerce_bool(
                item.get("dynamic_amount", item.get("is_dynamic", False))
            )
            result[str(package_id)] = CardPackage(
                package_id=str(package_id),
                credits=credits,
                prices=prices,
                offer_id=offer_id,
                dynamic_amount=dynamic_amount,
            )
        return result

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y"}
        return False

    @classmethod
    def package(cls, package_id: str) -> CardPackage:
        package = cls.packages().get(package_id)
        if package is None:
            raise UnknownPaymentPackageError(package_id)
        return package

    @classmethod
    async def provider_packages(cls) -> dict[str, CardPackage]:
        configured = cls.packages()
        if configured:
            return configured

        client = CardCheckoutClient(
            settings.card_api_key,
            settings.card_api_base_url,
            settings.card_webhook_key,
        )
        try:
            payload = await client.get_products()
        finally:
            await client.aclose()
        return cls._parse_lava_products(payload, settings.card_offer_id)

    @classmethod
    async def provider_package(cls, package_id: str) -> CardPackage:
        package = (await cls.provider_packages()).get(package_id)
        if package is None:
            raise UnknownPaymentPackageError(package_id)
        return package

    @classmethod
    async def resolve_invoice_offer(
        cls,
        client: CardCheckoutClient,
        package: CardPackage,
    ) -> CardOfferResolution:
        configured_id = str(package.offer_id or settings.card_offer_id or "").strip()
        if configured_id:
            try:
                payload = await client.get_products()
            except PaymentProviderError:
                return CardOfferResolution(configured_id, "configured")
            resolved = cls._resolve_configured_offer(payload, configured_id)
            if resolved is not None:
                return resolved
            return CardOfferResolution(configured_id, "configured")

        try:
            payload = await client.get_products()
        except PaymentProviderError as exc:
            raise PaymentProviderError(
                "Card checkout offer id is not configured and product lookup failed"
            ) from exc
        candidates = cls._dynamic_offer_ids(payload)
        if len(candidates) == 1:
            return CardOfferResolution(candidates[0], "single_dynamic_offer")
        raise PaymentProviderError(
            "Card checkout offer id is not configured; set CARD_OFFER_ID or package offer_id"
        )

    @classmethod
    def _resolve_configured_offer(
        cls,
        payload: dict[str, Any],
        configured_id: str,
    ) -> CardOfferResolution | None:
        product_match_offers: list[dict[str, Any]] = []
        for product in cls._products_from_payload(payload):
            product_id = cls._object_id(product, product_keys=True)
            offers = cls._offers_from_product(product)
            for offer in offers:
                offer_id = cls._object_id(offer, product_keys=False)
                if offer_id == configured_id:
                    return CardOfferResolution(offer_id, "offer_id")
            if product_id == configured_id:
                product_match_offers = offers

        if not product_match_offers:
            return None

        dynamic_offers = [
            offer
            for offer in product_match_offers
            if cls._object_id(offer, product_keys=False) and cls._is_dynamic_price_offer(offer)
        ]
        if len(dynamic_offers) == 1:
            return CardOfferResolution(
                cls._object_id(dynamic_offers[0], product_keys=False),
                "product_dynamic_offer",
            )

        available_offer_ids = [
            cls._object_id(offer, product_keys=False)
            for offer in product_match_offers
            if cls._object_id(offer, product_keys=False)
        ]
        if len(available_offer_ids) == 1:
            return CardOfferResolution(available_offer_ids[0], "product_single_offer")
        raise PaymentProviderError(
            "CARD_OFFER_ID points to a product with multiple offers; set exact package offer_id"
        )

    @classmethod
    def _parse_lava_products(cls, payload: dict[str, Any], configured_id: str) -> dict[str, CardPackage]:
        configured_id = configured_id.strip()
        result: dict[str, CardPackage] = {}
        for product in cls._products_from_payload(payload):
            product_id = cls._object_id(product, product_keys=True)
            product_matches = bool(configured_id and product_id == configured_id)
            for offer in cls._offers_from_product(product):
                offer_id = cls._object_id(offer, product_keys=False)
                if configured_id and not product_matches and offer_id != configured_id:
                    continue
                credits = cls._credits_from_offer(offer)
                prices = cls._prices_from_offer(offer)
                if not offer_id or credits is None or not prices:
                    continue
                result[offer_id] = CardPackage(
                    package_id=offer_id,
                    credits=credits,
                    prices=prices,
                    offer_id=offer_id,
                    dynamic_amount=False,
                )
        return result

    @classmethod
    def _dynamic_offer_ids(cls, payload: dict[str, Any]) -> list[str]:
        result: list[str] = []
        for product in cls._products_from_payload(payload):
            for offer in cls._offers_from_product(product):
                offer_id = cls._object_id(offer, product_keys=False)
                if offer_id and cls._is_dynamic_price_offer(offer):
                    result.append(offer_id)
        return result

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
        keys = ("id", "productId", "product_id") if product_keys else ("id", "offerId", "offer_id")
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @classmethod
    def _is_dynamic_price_offer(cls, offer: dict[str, Any]) -> bool:
        for key in cls.DYNAMIC_PRICE_KEYS:
            value = offer.get(key)
            if value is True:
                return True
            if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "on"}:
                return True
        text = " ".join(str(offer.get(key) or "") for key in ("type", "priceType", "paymentType"))
        normalized = text.lower().replace("_", "-")
        return "dynamic" in normalized or "custom" in normalized or "request" in normalized

    @staticmethod
    def _credits_from_offer(offer: dict[str, Any]) -> Decimal | None:
        for key in ("name", "title", "description"):
            match = re.search(r"(\d+(?:[.,]\d+)?)\s*ROX\b", str(offer.get(key) or ""), re.IGNORECASE)
            if match:
                value = Decimal(match.group(1).replace(",", "."))
                return value if value > 0 else None
        return None

    @classmethod
    def _prices_from_offer(cls, offer: dict[str, Any]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        raw_prices = offer.get("prices")
        if not isinstance(raw_prices, list):
            return result
        for item in raw_prices:
            if not isinstance(item, dict):
                continue
            currency = str(item.get("currency") or "").upper()
            if currency not in cls.CURRENCIES:
                continue
            amount_raw = item.get("amount")
            if amount_raw in (None, ""):
                continue
            amount = Decimal(str(amount_raw))
            if amount > 0:
                result[currency] = amount
        return result


class CardPaymentService:
    PROVIDER = "card"
    PUBLIC_LABEL = "Оплата картой"
    SUCCESS_STATUSES = frozenset({"success", "succeeded", "paid", "completed"})
    FAILED_STATUSES = frozenset({"failed", "cancelled", "canceled", "expired"})
    REFUNDED_STATUSES = frozenset({"refunded", "refund", "reversed"})
    # When a package does not pin an offer id, resolve_invoice_offer may pick a
    # dynamic-price offer from the provider catalog. Such resolutions still need
    # `amount` sent, so they must be treated as dynamic even without an explicit
    # package flag.
    DYNAMIC_RESOLUTION_SOURCES = frozenset(
        {"single_dynamic_offer", "product_dynamic_offer"}
    )

    @staticmethod
    def provider_configured() -> bool:
        return bool(settings.card_api_key)

    @staticmethod
    def _email(value: str) -> str:
        email = value.strip().lower()
        if (
            not email
            or len(email) > 254
            or " " in email
            or email.count("@") != 1
            or email.startswith("@")
            or email.endswith("@")
        ):
            raise ValueError("Введите корректный email для чека и платёжной страницы")
        return email

    @staticmethod
    def _route_for(currency: str) -> str | None:
        try:
            raw = json.loads(settings.card_payment_route_by_currency_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("CARD_PAYMENT_ROUTE_BY_CURRENCY_JSON must be a JSON object")
        value = str(raw.get(currency.upper()) or "").strip().upper() or None
        CardCheckoutClient.validate_route(currency, value)
        return value

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        package_id: str,
        currency: str,
        billing_email: str,
        request_key: str,
    ) -> Payment:
        currency = currency.upper()
        if currency not in CardCheckoutClient.SUPPORTED_CURRENCIES:
            raise ValueError("Поддерживаются только RUB, USD и EUR")
        if not request_key or len(request_key) > 64:
            raise ValueError("Idempotency key must contain 1-64 characters")
        email = cls._email(billing_email)
        package = await CardPackageCatalog.provider_package(package_id)
        amount = package.prices.get(currency)
        if amount is None:
            raise UnknownPaymentPackageError(f"{package_id}:{currency}")
        # Validate the operator-owned package before committing a local payment intent.
        # This avoids creation_unknown rows for prices the upstream API will always reject.
        CardCheckoutClient.validate_amount(currency, amount)
        bonus_credits = TopUpBonusService.bonus_for(package.credits)
        credited_credits = package.credits + bonus_credits

        existing_request = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.user_id == user_id,
                PaymentRequest.request_key == request_key,
            )
        )
        if existing_request is not None:
            existing_payment = await session.get(Payment, existing_request.payment_id)
            if (
                existing_request.provider != cls.PROVIDER
                or existing_request.package_id != package_id
                or existing_payment is None
                or existing_payment.currency.upper() != currency
            ):
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            return existing_payment

        payment = Payment(
            user_id=user_id,
            provider=cls.PROVIDER,
            amount=amount,
            currency=currency,
            rox_amount=credited_credits,
            status="creating",
            payload={
                "package_id": package_id,
                "request_key": request_key,
                "billing_email": email,
                "base_credits": str(package.credits),
                "bonus_credits": str(bonus_credits),
                "credited_credits": str(credited_credits),
                "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
            },
        )
        session.add(payment)
        await session.flush()
        request_row = PaymentRequest(
            user_id=user_id,
            payment_id=payment.id,
            request_key=request_key,
            provider=cls.PROVIDER,
            package_id=package_id,
            status="creating",
        )
        session.add(request_row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            winner = await session.scalar(
                select(PaymentRequest).where(
                    PaymentRequest.user_id == user_id,
                    PaymentRequest.request_key == request_key,
                )
            )
            if winner is None:
                raise
            existing_payment = await session.get(Payment, winner.payment_id)
            if (
                winner.provider != cls.PROVIDER
                or winner.package_id != package_id
                or existing_payment is None
                or existing_payment.currency.upper() != currency
            ):
                raise PaymentIdempotencyConflict(
                    "The idempotency key was already used for another payment intent"
                )
            return existing_payment

        route = cls._route_for(currency)
        client = CardCheckoutClient(
            settings.card_api_key,
            settings.card_api_base_url,
            settings.card_webhook_key,
        )
        try:
            offer = await CardPackageCatalog.resolve_invoice_offer(client, package)
            created = await client.create_invoice(
                email=email,
                offer_id=offer.offer_id,
                currency=currency,
                amount=(
                    amount
                    if package.dynamic_amount
                    or offer.source in cls.DYNAMIC_RESOLUTION_SOURCES
                    else None
                ),
                payment_provider=route,
            )
        except PaymentProviderValidationError as exc:
            payment = await session.get(Payment, payment.id)
            request_row = await session.get(PaymentRequest, request_row.id)
            if payment is not None:
                payment.status = "failed"
                payment.payload = {
                    **payment.payload,
                    "create_error": str(exc),
                    "provider_error_type": "validation",
                }
            if request_row is not None:
                request_row.status = "failed"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise
        except Exception as exc:
            payment = await session.get(Payment, payment.id)
            request_row = await session.get(PaymentRequest, request_row.id)
            if payment is not None:
                payment.status = "creation_unknown"
                payment.payload = {**payment.payload, "create_error": str(exc)}
            if request_row is not None:
                request_row.status = "unknown"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise
        finally:
            await client.aclose()

        payment = await session.get(Payment, payment.id)
        request_row = await session.get(PaymentRequest, request_row.id)
        if payment is None or request_row is None:
            raise LookupError("Payment disappeared after external invoice creation")
        payment.external_id = created.external_id
        payment.status = "pending"
        payment.payload = {
            **payment.payload,
            "payment_url": created.payment_url,
            "route": route or "hosted_checkout",
            "offer_id": offer.offer_id,
            "offer_id_source": offer.source,
            "provider_response": created.raw,
        }
        request_row.status = "completed"
        request_row.last_error = None
        await session.commit()
        return payment

    @classmethod
    async def complete(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        provider_payload: dict[str, Any],
    ) -> Payment:
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider mismatch")
        if payment.status in {"succeeded", "partially_refunded", "refunded"}:
            return payment

        wallet_tx = await WalletService.credit(
            session,
            user_id=payment.user_id,
            amount=Decimal(payment.rox_amount),
            kind="payment",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment:{payment.id}:credit",
        )
        # Referral accounting is RUB-denominated. Never treat a USD/EUR numeric
        # amount as RUB; use the product's paid ROX basis, excluding gift bonuses.
        payload = payment.payload or {}
        referral_credits = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        reward_basis_rub = InternalCreditService.rubles_for(referral_credits)
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=payment.user_id,
            source_transaction_id=wallet_tx.id,
            payment_amount=reward_basis_rub,
        )
        payment.status = "succeeded"
        payment.payload = {**payment.payload, "last_provider_state": provider_payload}
        await session.commit()
        return payment

    @classmethod
    async def reconcile(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        event_type: str | None = None,
    ) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider mismatch")
        if not payment.external_id:
            # Creation may have reached the provider before our process failed. The
            # API does not provide a merchant idempotency key for create-invoice, so
            # do not create a second invoice during reconciliation.
            if payment.status not in {"succeeded", "refunded"}:
                payment.status = "creation_unknown"
                await session.commit()
            return payment

        client = CardCheckoutClient(
            settings.card_api_key,
            settings.card_api_base_url,
            settings.card_webhook_key,
        )
        try:
            invoice = await client.get_invoice(str(payment.external_id))
        finally:
            await client.aclose()

        cls._assert_invoice(payment, invoice)
        status = CardCheckoutClient.extract_status(invoice)
        normalized_event = str(event_type or "").strip().lower()
        if normalized_event == "payment.success" or status in cls.SUCCESS_STATUSES:
            payment = await cls.complete(
                session,
                payment_id=payment.id,
                provider_payload=invoice,
            )
        elif normalized_event == "payment.failed" or status in cls.FAILED_STATUSES:
            if payment.status not in {"succeeded", "partially_refunded", "refunded"}:
                payment.status = "failed"
                payment.payload = {**payment.payload, "last_provider_state": invoice}
                await session.commit()
        elif payment.status not in {"succeeded", "partially_refunded", "refunded"}:
            payment.status = "pending"
            payment.payload = {**payment.payload, "last_provider_state": invoice}
            await session.commit()

        refunded = CardCheckoutClient.extract_refunded_amount(invoice)
        if refunded is not None and refunded > 0:
            already = await PaymentService.reversed_amount(session, payment.id)
            delta = refunded - already
            if delta > 0:
                payment = await PaymentService.apply_reversal(
                    session,
                    payment_id=payment.id,
                    amount=delta,
                    provider=cls.PROVIDER,
                    idempotency_key=f"card:cumulative:{payment.external_id}:{refunded}",
                    reason="refund",
                    provider_payload=invoice,
                    provider_event_id=None,
                )
        elif status in cls.REFUNDED_STATUSES and payment.status in {
            "succeeded",
            "partially_refunded",
        }:
            # Official docs say refund webhooks are not emitted. If the invoice marks
            # itself refunded but omits the cumulative amount, keep it in manual review
            # instead of guessing how many credits to debit.
            payment.status = "refund_review"
            payment.payload = {
                **payment.payload,
                "refund_review": True,
                "last_provider_state": invoice,
            }
            await session.commit()
        return payment

    @staticmethod
    def _assert_invoice(payment: Payment, invoice: dict[str, Any]) -> None:
        external_id = CardCheckoutClient.extract_invoice_id(invoice)
        if external_id and external_id != str(payment.external_id):
            raise PaymentProviderError("Card checkout invoice id mismatch")
        amount = CardCheckoutClient.extract_amount(invoice)
        if amount is not None and amount != Decimal(payment.amount):
            raise PaymentProviderError("Card checkout amount mismatch")
        currency = CardCheckoutClient.extract_currency(invoice)
        if currency is not None and currency != payment.currency.upper():
            raise PaymentProviderError("Card checkout currency mismatch")

    @staticmethod
    async def source_payment_transaction(
        session: AsyncSession,
        payment: Payment,
    ) -> WalletTransaction | None:
        return await session.scalar(
            select(WalletTransaction).where(
                WalletTransaction.user_id == payment.user_id,
                WalletTransaction.kind == "payment",
                WalletTransaction.reference_type == "payment",
                WalletTransaction.reference_id == str(payment.id),
            )
        )
