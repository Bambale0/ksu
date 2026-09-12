from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment
from app.db.payment_models import PaymentRequest
from app.providers.payment_2328 import (
    FINAL_FAILURE_STATUSES,
    PENDING_STATUSES,
    SUCCESS_STATUSES,
    Payment2328Client,
)
from app.providers.payments import PaymentProviderError
from app.services.admin_security import utcnow
from app.services.card_payments import CardPackage, CardPackageCatalog
from app.services.credits import InternalCreditService
from app.services.payment_bonuses import TopUpBonusService
from app.services.payment_creation import PaymentCreationLifecycle
from app.services.payments import PaymentService, UnknownPaymentPackageError


class Payment2328Service:
    PROVIDER = "2328"
    PUBLIC_LABEL = "Криптовалюта"
    CURRENCY = "RUB"
    RECONCILABLE_STATUSES = frozenset(
        {"creating", "creation_unknown", "pending", "refund_review"}
    )

    @staticmethod
    def provider_configured() -> bool:
        return bool(
            settings.payment_2328_project_uuid
            and settings.payment_2328_api_key
            and settings.webhook_url("webhooks/payments/2328")
        )

    @classmethod
    async def provider_packages(cls) -> dict[str, CardPackage]:
        packages = await CardPackageCatalog.provider_packages()
        return {
            package_id: package
            for package_id, package in packages.items()
            if cls.CURRENCY in package.prices
        }

    @classmethod
    async def provider_package(cls, package_id: str) -> CardPackage:
        package = (await cls.provider_packages()).get(package_id)
        if package is None:
            raise UnknownPaymentPackageError(package_id)
        return package

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        package_id: str,
        request_key: str,
    ) -> Payment:
        if not cls.provider_configured():
            raise PaymentProviderError("2328.io is not configured")
        PaymentCreationLifecycle.validate_request_key(request_key)

        package = await cls.provider_package(package_id)
        amount = package.prices.get(cls.CURRENCY)
        if amount is None:
            raise UnknownPaymentPackageError(package_id)

        base_credits = Decimal(package.credits)
        bonus_credits = TopUpBonusService.bonus_for(base_credits)
        credited_credits = base_credits + bonus_credits
        payment = Payment(
            user_id=user_id,
            provider=cls.PROVIDER,
            amount=amount,
            currency=cls.CURRENCY,
            rox_amount=credited_credits,
            status="creating",
            payload={
                "package_id": package_id,
                "request_key": request_key,
                "base_credits": str(base_credits),
                "bonus_credits": str(bonus_credits),
                "credited_credits": str(credited_credits),
                "internal_credit_rub": str(InternalCreditService.rub_per_credit()),
            },
        )
        creation = await PaymentCreationLifecycle.begin(
            session,
            payment=payment,
            user_id=user_id,
            provider=cls.PROVIDER,
            package_id=package_id,
            request_key=request_key,
        )
        if not creation.created:
            return creation.payment
        assert creation.request_id is not None
        payment = creation.payment

        client = cls._client()
        try:
            created = await client.create_payment(
                local_id=str(payment.id),
                amount=amount,
                currency=cls.CURRENCY,
                description=f"Пополнение ROXY: {base_credits} ROX",
                callback_url=settings.webhook_url("webhooks/payments/2328"),
            )
        except Exception as exc:
            await PaymentCreationLifecycle.mark_unknown(
                session,
                payment_id=payment.id,
                request_id=creation.request_id,
                error=exc,
            )
            raise
        finally:
            await client.aclose()

        return await PaymentCreationLifecycle.mark_pending(
            session,
            payment_id=payment.id,
            request_id=creation.request_id,
            created=created,
            missing_message="Payment disappeared after 2328.io payment creation",
            refresh=True,
        )

    @classmethod
    async def reconcile(cls, session: AsyncSession, *, payment_id: uuid.UUID) -> Payment:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider is not 2328.io")

        client = cls._client()
        try:
            state = await client.get_payment_info(
                external_id=str(payment.external_id) if payment.external_id else None,
                order_id=None if payment.external_id else str(payment.id),
            )
        finally:
            await client.aclose()
        if state is None:
            # 2328 checkout invoices are created with a one-hour TTL. A 404 is
            # recoverable immediately after an ambiguous create, but treating it as
            # recoverable forever leaves stale intents in the polling queue.
            #
            # Reload and lock after the network call: a webhook can complete/refund
            # the payment while we are waiting for the provider. Never overwrite a
            # terminal state with "expired".
            payment = await session.get(
                Payment,
                payment_id,
                populate_existing=True,
                with_for_update=True,
            )
            if payment is None:
                raise LookupError("Payment not found")
            if payment.status not in cls.RECONCILABLE_STATUSES:
                return payment

            age_seconds = max(
                0.0,
                (utcnow() - payment.created_at).total_seconds(),
            )
            if age_seconds >= max(0, settings.payment_2328_missing_grace_seconds):
                error = "2328.io payment was not found after the recovery grace period"
                payment.status = "expired"
                payment.payload = {
                    **(payment.payload or {}),
                    "reconciliation_terminal_error": {
                        "reason": "provider_not_found_after_grace",
                        "error": error,
                        "recorded_at": utcnow().isoformat(),
                    },
                }
                request_row = await session.scalar(
                    select(PaymentRequest).where(PaymentRequest.payment_id == payment.id)
                )
                if request_row is not None and request_row.status in {"creating", "unknown"}:
                    request_row.status = "failed"
                    request_row.last_error = error
                await session.commit()
            return payment
        return await cls.apply_state(session, payment=payment, provider_payload=state)

    @classmethod
    async def apply_state(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        provider_payload: dict[str, Any],
    ) -> Payment:
        if payment.provider != cls.PROVIDER:
            raise PaymentProviderError("Payment provider is not 2328.io")
        if str(provider_payload.get("order_id") or "") != str(payment.id):
            raise PaymentProviderError("2328.io order_id mismatch")

        external_id = str(provider_payload.get("uuid") or "")
        if not external_id:
            raise PaymentProviderError("2328.io payment UUID is missing")
        if payment.external_id and str(payment.external_id) != external_id:
            raise PaymentProviderError("2328.io payment UUID mismatch")
        if not payment.external_id:
            payment.external_id = external_id

        PaymentService.assert_amount(
            payment,
            amount=Decimal(str(provider_payload.get("amount") or "0")),
            currency=str(provider_payload.get("currency") or ""),
        )
        provider_status = str(provider_payload.get("payment_status") or "").lower()
        request_row = await session.scalar(
            select(PaymentRequest).where(PaymentRequest.payment_id == payment.id)
        )
        if request_row is not None and request_row.status == "unknown":
            request_row.status = "completed"
            request_row.last_error = None

        if provider_status in SUCCESS_STATUSES:
            return await PaymentService.complete(
                session,
                payment_id=payment.id,
                provider_payload=provider_payload,
            )

        if payment.status not in PaymentService.TERMINAL_STATUSES:
            if provider_status == "cancel":
                payment.status = "expired"
            elif provider_status in {"underpaid", "aml_lock"}:
                payment.status = "failed"
            elif provider_status in PENDING_STATUSES or not provider_status:
                payment.status = "pending"
            elif provider_status in FINAL_FAILURE_STATUSES:
                payment.status = "failed"
            else:
                raise PaymentProviderError(f"Unknown 2328.io payment status: {provider_status}")
            payment.payload = {
                **(payment.payload or {}),
                "last_provider_state": provider_payload,
            }
            await session.commit()
        return payment

    @staticmethod
    def _client() -> Payment2328Client:
        return Payment2328Client(
            settings.payment_2328_project_uuid,
            settings.payment_2328_api_key,
            settings.payment_2328_base_url,
        )
