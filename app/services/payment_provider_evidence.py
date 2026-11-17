"""Bounded, non-mutating provider evidence lookups for unresolved KSU payments.

Only authoritative *status inquiries* are permitted. No create, cancel, refund,
credit or reconciliation methods are called. An observed provider status is NOT
operator authorization to change an existing payment or wallet record.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payment_2328 import (
    FINAL_FAILURE_STATUSES,
    PENDING_STATUSES,
    SUCCESS_STATUSES,
    Payment2328Client,
)
from app.providers.payments import CryptoPayClient, TBankClient
from app.services.admin_security import utcnow
from app.services.card_payments import CardPaymentService
from app.services.payment_backlog import PaymentBacklogReport


class ProviderEvidenceProbe:
    """Classify bounded identity-verified provider observations, never settle."""

    SUPPORTED_PROVIDERS = frozenset({"card", "cryptobot", "tbank", "2328"})
    MAX_LOOKUPS = 5

    @classmethod
    async def candidates(
        cls,
        session: AsyncSession,
        *,
        provider: str,
        limit: int = 3,
        older_than_days: int = 7,
    ) -> list[Payment]:
        if provider not in cls.SUPPORTED_PROVIDERS:
            raise ValueError("unsupported provider")
        if not 1 <= limit <= cls.MAX_LOOKUPS:
            raise ValueError("limit must be between 1 and 5")
        if not 1 <= older_than_days <= 3650:
            raise ValueError("older_than_days must be between 1 and 3650")
        query = (
            select(Payment)
            .where(
                Payment.provider == provider,
                Payment.status.in_(PaymentBacklogReport.OPEN_STATUSES),
                Payment.external_id.is_not(None),
                Payment.updated_at < utcnow() - timedelta(days=older_than_days),
            )
            .order_by(Payment.updated_at.asc(), Payment.id.asc())
            .limit(limit)
        )
        return list((await session.scalars(query)).all())

    @staticmethod
    def _amount_matches(payment: Payment, value: object, currency: object) -> bool:
        if isinstance(value, bool) or isinstance(currency, (dict, list)):
            return False
        if value is None or not isinstance(currency, str):
            return False
        try:
            actual = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return False
        return (
            actual.is_finite()
            and actual == Decimal(str(payment.amount))
            and currency.upper() == payment.currency.upper()
        )

    @classmethod
    def classify_verified_response(
        cls, payment: Payment, response: dict[str, Any] | None
    ) -> str:
        """Fail closed if ownership or monetary evidence is incomplete.

        No model objects or database session state is ever mutated.
        """
        if response is None:
            return "provider_not_found_unproven"
        if not isinstance(response, dict) or not payment.external_id:
            return "identity_unverified"
        provider = payment.provider
        expected_external = str(payment.external_id)
        status = ""
        if provider == "card":
            try:
                CardPaymentService._assert_invoice(
                    payment, response, require_identity=True
                )
            except Exception:
                return "identity_unverified"
            if CardCheckoutClient.extract_invoice_id(response) != expected_external:
                return "identity_unverified"
            local_email = str(
                (payment.payload or {}).get("billing_email") or ""
            ).strip().lower()
            remote_email = CardCheckoutClient.extract_buyer_email(response)
            if local_email and local_email != remote_email:
                return "identity_unverified"
            status = CardCheckoutClient.extract_status(response)
            if status in CardPaymentService.SUCCESS_STATUSES:
                return "verified_provider_paid"
            if status in CardPaymentService.REFUNDED_STATUSES:
                return "provider_refund_evidence"
            if status in CardPaymentService.FAILED_STATUSES:
                return "verified_provider_terminal"
            if status in {"pending", "new", "processing"}:
                return "verified_provider_pending"
        elif provider == "cryptobot":
            if (
                str(response.get("invoice_id") or "") != expected_external
                or str(response.get("payload") or "") != str(payment.id)
                or not cls._amount_matches(
                    payment, response.get("amount"), response.get("fiat")
                )
            ):
                return "identity_unverified"
            status = str(response.get("status") or "").strip().lower()
            if status == "paid":
                return "verified_provider_paid"
            if status == "expired":
                return "verified_provider_terminal"
            if status == "active":
                return "verified_provider_pending"
        elif provider == "tbank":
            amount = response.get("Amount")
            if (
                str(response.get("PaymentId") or "") != expected_external
                or str(response.get("OrderId") or "") != str(payment.id)
                or payment.currency.upper() != "RUB"
                or isinstance(amount, bool)
                or amount is None
            ):
                return "identity_unverified"
            try:
                cents = Decimal(str(amount))
            except (ValueError, InvalidOperation):
                return "identity_unverified"
            if (
                not cents.is_finite()
                or cents != Decimal(str(payment.amount)) * 100
            ):
                return "identity_unverified"
            status = str(response.get("Status") or "").strip().upper()
            if status == "CONFIRMED":
                return "verified_provider_paid"
            if status in {"REFUNDED", "REVERSED"}:
                return "provider_refund_evidence"
            if status in {"REJECTED", "DEADLINE_EXPIRED", "CANCELED"}:
                return "verified_provider_terminal"
            if status in {"NEW", "FORM_SHOWED", "AUTHORIZED"}:
                return "verified_provider_pending"
        elif provider == "2328":
            if (
                str(response.get("uuid") or "") != expected_external
                or str(response.get("order_id") or "") != str(payment.id)
                or not cls._amount_matches(
                    payment, response.get("amount"), response.get("currency")
                )
            ):
                return "identity_unverified"
            status = str(response.get("payment_status") or "").strip().lower()
            if status in SUCCESS_STATUSES:
                return "verified_provider_paid"
            if status in FINAL_FAILURE_STATUSES:
                return "verified_provider_terminal"
            if status in PENDING_STATUSES:
                return "verified_provider_pending"
        else:
            return "unsupported_provider"
        return "provider_status_unrecognized"

    @staticmethod
    async def lookup_status(payment: Payment) -> dict[str, Any] | None:
        """Call only the provider's read-only invoice/status inquiry endpoint."""
        external_id = str(payment.external_id or "")
        if not external_id:
            raise ValueError("provider invoice id missing")
        if payment.provider == "card":
            client = CardCheckoutClient(
                settings.card_api_key, settings.card_api_base_url,
                settings.card_webhook_key,
            )
            get = lambda: client.get_invoice(external_id)
        elif payment.provider == "cryptobot":
            client = CryptoPayClient(
                settings.cryptopay_api_token, settings.cryptopay_base_url
            )
            get = lambda: client.get_invoice(external_id)
        elif payment.provider == "tbank":
            client = TBankClient(
                settings.tbank_terminal_key, settings.tbank_password,
                settings.tbank_base_url,
            )
            # T-Bank exposes its non-mutating GetState query over HTTP POST.
            get = lambda: client.get_state(external_id)
        elif payment.provider == "2328":
            client = Payment2328Client(
                settings.payment_2328_project_uuid,
                settings.payment_2328_api_key,
                settings.payment_2328_base_url,
            )
            # /v1/payment/info is a status query despite using HTTP POST.
            get = lambda: client.get_payment_info(external_id=external_id)
        else:
            raise ValueError("unsupported provider")
        try:
            return await get()
        finally:
            await client.aclose()

    @classmethod
    async def probe(cls, payment: Payment) -> str:
        try:
            response = await cls.lookup_status(payment)
        except Exception:
            # Never log exception text: upstream errors can include invoice IDs,
            # token-bearing URLs, payment details and sensitive response bodies.
            return "provider_lookup_unavailable"
        try:
            return cls.classify_verified_response(payment, response)
        except Exception:
            # Malformed provider evidence is NOT an authoritative terminal
            # state, even when the provider returned HTTP 200.
            return "identity_unverified"
