from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.providers.payments import CreatedPayment


class PaymentIdempotencyConflict(ValueError):
    pass


PaymentMatch = Callable[[Payment], bool]


@dataclass(frozen=True, slots=True)
class PaymentCreationResult:
    payment: Payment
    request_id: uuid.UUID | None
    created: bool


class PaymentCreationLifecycle:
    """Own the durable local half of payment creation across providers.

    Provider adapters keep package/provider-specific request construction. This
    module owns the invariant sequence around that side effect:

    local Payment + PaymentRequest -> durable commit -> provider call
    -> unknown/failed or pending.
    """

    @staticmethod
    def validate_request_key(request_key: str) -> None:
        if not request_key or len(request_key) > 64:
            raise ValueError("Idempotency key must contain 1-64 characters")

    @classmethod
    async def begin(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        user_id: uuid.UUID,
        provider: str,
        package_id: str,
        request_key: str,
        payment_match: PaymentMatch | None = None,
    ) -> PaymentCreationResult:
        cls.validate_request_key(request_key)

        existing = await cls._existing_payment(
            session,
            user_id=user_id,
            provider=provider,
            package_id=package_id,
            request_key=request_key,
            payment_match=payment_match,
        )
        if existing is not None:
            return PaymentCreationResult(existing, None, False)

        session.add(payment)
        await session.flush()
        request_row = PaymentRequest(
            user_id=user_id,
            payment_id=payment.id,
            request_key=request_key,
            provider=provider,
            package_id=package_id,
            status="creating",
        )
        session.add(request_row)
        try:
            # The local intent must be durable before the external side effect.
            await session.commit()
        except IntegrityError:
            await session.rollback()
            winner = await cls._existing_payment(
                session,
                user_id=user_id,
                provider=provider,
                package_id=package_id,
                request_key=request_key,
                payment_match=payment_match,
            )
            if winner is None:
                raise
            return PaymentCreationResult(winner, None, False)

        return PaymentCreationResult(payment, request_row.id, True)

    @classmethod
    async def mark_unknown(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        request_id: uuid.UUID,
        error: Exception,
    ) -> None:
        payment = await session.get(Payment, payment_id)
        request_row = await session.get(PaymentRequest, request_id)
        if payment is not None:
            payment.status = "creation_unknown"
            payment.payload = {**(payment.payload or {}), "create_error": str(error)}
        if request_row is not None:
            request_row.status = "unknown"
            request_row.last_error = str(error)[:4000]
        await session.commit()

    @classmethod
    async def mark_failed(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        request_id: uuid.UUID,
        error: Exception,
        payload_updates: Mapping[str, Any] | None = None,
    ) -> None:
        payment = await session.get(Payment, payment_id)
        request_row = await session.get(PaymentRequest, request_id)
        if payment is not None:
            payment.status = "failed"
            payment.payload = {
                **(payment.payload or {}),
                "create_error": str(error),
                **dict(payload_updates or {}),
            }
        if request_row is not None:
            request_row.status = "failed"
            request_row.last_error = str(error)[:4000]
        await session.commit()

    @classmethod
    async def mark_pending(
        cls,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        request_id: uuid.UUID,
        created: CreatedPayment,
        payload_updates: Mapping[str, Any] | None = None,
        missing_message: str = "Payment disappeared after provider creation",
        refresh: bool = False,
    ) -> Payment:
        payment = await session.get(Payment, payment_id)
        request_row = await session.get(PaymentRequest, request_id)
        if payment is None or request_row is None:
            raise LookupError(missing_message)

        payment.external_id = created.external_id
        payment.status = "pending"
        payment.payload = {
            **(payment.payload or {}),
            "payment_url": created.payment_url,
            **dict(payload_updates or {}),
            "provider_response": created.raw,
        }
        request_row.status = "completed"
        request_row.last_error = None
        await session.commit()
        if refresh:
            await session.refresh(payment)
        return payment

    @classmethod
    async def _existing_payment(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        provider: str,
        package_id: str,
        request_key: str,
        payment_match: PaymentMatch | None,
    ) -> Payment | None:
        request_row = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.user_id == user_id,
                PaymentRequest.request_key == request_key,
            )
        )
        if request_row is None:
            return None
        if request_row.provider != provider or request_row.package_id != package_id:
            raise PaymentIdempotencyConflict(
                "The idempotency key was already used for another payment intent"
            )

        payment = await session.get(Payment, request_row.payment_id)
        if payment is None:
            raise LookupError("Idempotent payment record is inconsistent")
        if payment_match is not None and not payment_match(payment):
            raise PaymentIdempotencyConflict(
                "The idempotency key was already used for another payment intent"
            )
        return payment
