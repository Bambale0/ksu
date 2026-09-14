from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, Payment
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.card_payments import CardPaymentService
from app.services.payment_refunds import PaymentRefundService
from app.services.payments import PaymentService


class AdminPaymentService:
    @staticmethod
    async def recheck(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        payment_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "payments.recheck", confirmed=True)

        async def operation() -> dict[str, Any]:
            payment = await session.get(Payment, payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            if payment.provider == CardPaymentService.PROVIDER:
                updated = await CardPaymentService.reconcile(session, payment_id=payment.id)
            else:
                updated = await PaymentService.reconcile(session, payment_id=payment.id)
            return {
                "id": str(updated.id),
                "provider": updated.provider,
                "status": updated.status,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="payments.recheck",
            target_id=str(payment_id),
            request_payload={},
            operation=operation,
        )

    @staticmethod
    async def reprocess(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        payment_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        """Re-run authoritative provider reconciliation without direct balance mutation.

        Provider completion is already idempotent in the payment domain. This
        command never performs a raw wallet credit, so a succeeded payment cannot
        be double-credited by reprocessing it.
        """

        AdminPolicy.authorize_action(
            admin,
            "payments.reprocess",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )

        async def operation() -> dict[str, Any]:
            payment = await session.get(Payment, payment_id)
            if payment is None:
                raise LookupError("Payment not found")
            before = payment.status
            if payment.provider == CardPaymentService.PROVIDER:
                updated = await CardPaymentService.reconcile(session, payment_id=payment.id)
            else:
                updated = await PaymentService.reconcile(session, payment_id=payment.id)
            return {
                "id": str(updated.id),
                "provider": updated.provider,
                "status_before": before,
                "status": updated.status,
                "balance_mutation": "provider-domain-idempotent",
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="payments.reprocess",
            target_id=str(payment_id),
            request_payload={},
            operation=operation,
        )

    @staticmethod
    async def refund(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        payment_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "payments.refund",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        if amount <= 0:
            raise ValueError("Refund amount must be positive")
        clean_reason = reason.strip()
        if len(clean_reason) < 3:
            raise ValueError("Refund reason is required")

        command, replayed = await AdminCommandLedger.reserve(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="payments.refund",
            target_id=str(payment_id),
            request_payload={"amount": str(amount), "reason": clean_reason},
        )
        if replayed:
            return AdminCommandLedger.replay(command), True

        # Persist the command before a provider side effect. PaymentRefundService
        # intentionally owns its own durable provider request lifecycle.
        await session.commit()
        provider_request_key = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"ksu-admin-refund:{idempotency_key}",
        ).hex
        try:
            refund = await PaymentRefundService.initiate(
                session,
                payment_id=payment_id,
                amount=amount,
                request_key=provider_request_key,
                reason=clean_reason,
            )
            response = {
                "id": str(refund.id),
                "payment_id": str(refund.payment_id),
                "provider": refund.provider,
                "provider_refund_id": refund.provider_refund_id,
                "amount": str(refund.amount),
                "currency": refund.currency,
                "status": refund.status,
                "reason": refund.reason,
            }
            await AdminCommandLedger.complete(session, command, response)
            await session.commit()
            return response, False
        except BaseException as exc:
            await session.rollback()
            command = await session.get(type(command), command.id)
            if command is not None:
                await AdminCommandLedger.fail(session, command, exc)
                await session.commit()
            raise

