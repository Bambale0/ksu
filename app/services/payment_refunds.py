from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_models import PaymentRefundRequest
from app.providers.payments import PaymentProviderError, TBankClient
from app.services.payments import (
    PaymentIdempotencyConflict,
    PaymentService,
    UnsupportedPaymentOperation,
)


class PaymentRefundService:
    @classmethod
    async def initiate(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        amount: Decimal,
        request_key: str,
        reason: str,
    ) -> PaymentRefundRequest:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider == "yookassa":
            return await PaymentService.initiate_refund(
                session,
                payment_id=payment_id,
                amount=amount,
                request_key=request_key,
                reason=reason,
            )
        if payment.provider == "tbank":
            return await cls._initiate_tbank_full(
                session,
                payment=payment,
                amount=amount,
                request_key=request_key,
                reason=reason,
            )
        raise UnsupportedPaymentOperation(
            "Crypto Pay invoice API does not expose a merchant refund operation"
        )

    @staticmethod
    async def _initiate_tbank_full(
        session: AsyncSession,
        *,
        payment: Payment,
        amount: Decimal,
        request_key: str,
        reason: str,
    ) -> PaymentRefundRequest:
        if payment.status != "succeeded":
            raise PaymentProviderError("T-Bank full refund requires a succeeded payment")
        already_reversed = await PaymentService.reversed_amount(session, payment.id)
        if already_reversed != Decimal("0") or amount != Decimal(payment.amount):
            raise UnsupportedPaymentOperation(
                "T-Bank admin refund currently supports only a full original-payment refund"
            )
        if not payment.external_id:
            raise PaymentProviderError("Payment has no T-Bank PaymentId")

        existing = await session.scalar(
            select(PaymentRefundRequest).where(
                PaymentRefundRequest.payment_id == payment.id,
                PaymentRefundRequest.request_key == request_key,
            )
        )
        if existing is not None:
            if Decimal(existing.amount) != amount:
                raise PaymentIdempotencyConflict(
                    "Refund idempotency key was already used for another amount"
                )
            return existing

        request_row = PaymentRefundRequest(
            payment_id=payment.id,
            request_key=request_key,
            provider="tbank",
            provider_refund_id=str(payment.external_id),
            amount=amount,
            currency=payment.currency,
            status="creating",
            reason=reason[:255],
        )
        session.add(request_row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            winner = await session.scalar(
                select(PaymentRefundRequest).where(
                    PaymentRefundRequest.payment_id == payment.id,
                    PaymentRefundRequest.request_key == request_key,
                )
            )
            if winner is None:
                raise
            if Decimal(winner.amount) != amount:
                raise PaymentIdempotencyConflict(
                    "Refund idempotency key was already used for another amount"
                )
            return winner

        client = TBankClient(
            settings.tbank_terminal_key,
            settings.tbank_password,
            settings.tbank_base_url,
        )
        try:
            provider_state = await client.refund_full(
                external_id=str(payment.external_id),
                request_key=request_key,
            )
        except Exception as exc:
            request_row = await session.get(PaymentRefundRequest, request_row.id)
            if request_row is not None:
                request_row.status = "unknown"
                request_row.last_error = str(exc)[:4000]
            await session.commit()
            raise
        finally:
            await client.aclose()

        request_row = await session.get(PaymentRefundRequest, request_row.id)
        if request_row is None:
            raise LookupError("Refund request disappeared")
        provider_payment_id = str(provider_state.get("PaymentId") or "")
        if provider_payment_id and provider_payment_id != str(payment.external_id):
            raise PaymentProviderError("T-Bank refund PaymentId mismatch")
        request_row.status = str(provider_state.get("Status") or "submitted").lower()
        request_row.provider_payload = provider_state
        request_row.last_error = None
        await session.commit()

        await PaymentService.apply_tbank_state(session, payment.id, provider_state)
        return request_row
