from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError


class CardPaymentRecoveryService:
    """Bind a provider contract only when authoritative data has one local match.

    The provider create endpoint has no merchant idempotency key in the contract
    ROXY currently relies on. If the create response is lost, issuing another
    create request can double-charge. Recovery therefore starts from the
    provider contract id delivered by a webhook and binds it only when amount,
    currency and buyer email identify exactly one unresolved local intent.
    """

    PROVIDER = "card"
    RECOVERABLE_STATUSES = frozenset({"creating", "creation_unknown", "pending"})

    @staticmethod
    def _payment_email(payment: Payment) -> str:
        return str((payment.payload or {}).get("billing_email") or "").strip().lower()

    @classmethod
    async def recover_missing_external_id(
        cls,
        session: AsyncSession,
        *,
        external_id: str,
    ) -> Payment:
        external_id = external_id.strip()
        if not external_id:
            raise PaymentProviderError("Card checkout invoice id is missing")

        existing = await session.scalar(
            select(Payment).where(
                Payment.provider == cls.PROVIDER,
                Payment.external_id == external_id,
            )
        )
        if existing is not None:
            return existing

        client = CardCheckoutClient(
            settings.card_api_key,
            settings.card_api_base_url,
            settings.card_webhook_key,
        )
        try:
            invoice = await client.get_invoice(external_id)
        finally:
            await client.aclose()

        invoice_id = CardCheckoutClient.extract_invoice_id(invoice)
        amount = CardCheckoutClient.extract_amount(invoice)
        currency = CardCheckoutClient.extract_currency(invoice)
        buyer_email = CardCheckoutClient.extract_buyer_email(invoice)
        if invoice_id != external_id:
            raise PaymentProviderError("Card checkout invoice id mismatch during recovery")
        if amount is None or currency is None or not buyer_email:
            raise PaymentProviderError(
                "Card checkout invoice is missing recovery identity fields"
            )

        rows = list(
            (
                await session.scalars(
                    select(Payment).where(
                        Payment.provider == cls.PROVIDER,
                        Payment.external_id.is_(None),
                        Payment.status.in_(cls.RECOVERABLE_STATUSES),
                        Payment.amount == Decimal(amount),
                        Payment.currency == currency,
                    )
                )
            ).all()
        )
        candidates = [row for row in rows if cls._payment_email(row) == buyer_email]
        if not candidates:
            raise LookupError("Recoverable card payment not found")
        if len(candidates) != 1:
            raise PaymentProviderError("Card checkout recovery is ambiguous")

        payment = await session.scalar(
            select(Payment).where(Payment.id == candidates[0].id).with_for_update()
        )
        if payment is None:
            raise LookupError("Recoverable card payment not found")
        if payment.external_id:
            if payment.external_id == external_id:
                return payment
            raise PaymentProviderError("Card payment was already bound to another invoice")
        if payment.status not in cls.RECOVERABLE_STATUSES:
            raise PaymentProviderError("Card payment is no longer recoverable")
        if Decimal(payment.amount) != amount:
            raise PaymentProviderError("Card checkout amount mismatch during recovery")
        if payment.currency.upper() != currency:
            raise PaymentProviderError("Card checkout currency mismatch during recovery")
        if cls._payment_email(payment) != buyer_email:
            raise PaymentProviderError("Card checkout buyer mismatch during recovery")

        payment.external_id = external_id
        payment.status = "pending"
        payment.payload = {
            **(payment.payload or {}),
            "recovered_external_id": True,
            "recovery_source": "authoritative_invoice",
            "last_provider_state": invoice,
        }
        request_row = await session.scalar(
            select(PaymentRequest)
            .where(PaymentRequest.payment_id == payment.id)
            .with_for_update()
        )
        if request_row is not None and request_row.status in {"creating", "unknown"}:
            request_row.status = "completed"
            request_row.last_error = None

        await session.commit()
        return payment
