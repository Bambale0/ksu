from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, Generation, WalletTransaction
from app.services.admin_commands import AdminCommandLedger, redact_secrets
from app.services.admin_policy import AdminPolicy
from app.services.generation_reliability import GenerationOutboxService
from app.services.wallet import WalletService


class AdminGenerationOperationService:
    @staticmethod
    async def list_operations(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "operations.read")
        stmt = select(Generation)
        if status:
            stmt = stmt.where(Generation.status == status)
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(Generation.created_at.desc())
                    .offset(max(0, min(offset, 100_000)))
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        return {"items": [AdminGenerationOperationService._view(item) for item in rows]}

    @staticmethod
    def _view(item: Generation) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "user_id": str(item.user_id),
            "kind": item.kind,
            "status": item.status,
            "provider": item.provider,
            "external_id": item.external_id,
            "cost_credits": str(item.cost_rox),
            "prompt": item.prompt[:1000],
            "input_url": item.input_url,
            "result_url": item.result_url,
            "error": item.error[:1000] if item.error else None,
            "parameters": redact_secrets(item.parameters or {}),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def get_operation(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        operation_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "operations.read")
        item = await session.get(Generation, operation_id)
        if item is None:
            raise LookupError("Operation not found")
        result = AdminGenerationOperationService._view(item)
        result["timeline"] = await AdminGenerationOperationService.timeline(
            session,
            admin=admin,
            operation_id=operation_id,
        )
        return result

    @staticmethod
    async def timeline(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        operation_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        AdminPolicy.require_permission(admin, "operations.read")
        item = await session.get(Generation, operation_id)
        if item is None:
            raise LookupError("Operation not found")
        transactions = list(
            (
                await session.scalars(
                    select(WalletTransaction)
                    .where(
                        WalletTransaction.reference_id == str(operation_id),
                        WalletTransaction.reference_type.in_(["generation", "generation_refund"]),
                    )
                    .order_by(WalletTransaction.created_at.asc())
                )
            ).all()
        )
        events: list[dict[str, Any]] = [
            {
                "type": "operation_created",
                "at": item.created_at.isoformat(),
                "status": "queued",
            }
        ]
        for tx in transactions:
            events.append(
                {
                    "type": "wallet",
                    "at": tx.created_at.isoformat(),
                    "kind": tx.kind,
                    "amount": str(tx.amount),
                    "balance_after": str(tx.balance_after),
                }
            )
        if item.updated_at != item.created_at:
            events.append(
                {
                    "type": "operation_updated",
                    "at": item.updated_at.isoformat(),
                    "status": item.status,
                    "error": item.error[:1000] if item.error else None,
                }
            )
        events.sort(key=lambda event: str(event["at"]))
        return events

    @staticmethod
    async def replay_operation(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        operation_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "operations.replay",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )

        async def operation() -> dict[str, Any]:
            source = await session.get(Generation, operation_id)
            if source is None:
                raise LookupError("Operation not found")
            params = dict(source.parameters or {})
            params["_admin_replay_of"] = str(source.id)
            params["_original_cost_rox"] = str(source.cost_rox)
            child = Generation(
                user_id=source.user_id,
                kind=source.kind,
                status="queued",
                prompt=source.prompt,
                input_url=source.input_url,
                result_url=None,
                cost_rox=Decimal("0"),
                provider=source.provider,
                external_id=None,
                error=None,
                parameters=params,
            )
            session.add(child)
            await session.flush()
            GenerationOutboxService.add(session, child.id)
            await session.flush()
            return {
                "operation_id": str(source.id),
                "child_operation_id": str(child.id),
                "status": child.status,
                "charged_credits": "0",
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="operations.replay",
            target_id=str(operation_id),
            request_payload={},
            operation=operation,
        )

    @staticmethod
    async def refund_operation(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        operation_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
        reason: str,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "operations.refund",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        payload = {"reason": reason}

        async def operation() -> dict[str, Any]:
            source = await session.get(Generation, operation_id)
            if source is None:
                raise LookupError("Operation not found")
            original_charge = await session.scalar(
                select(WalletTransaction).where(
                    WalletTransaction.reference_type == "generation",
                    WalletTransaction.reference_id == str(source.id),
                    WalletTransaction.user_id == source.user_id,
                )
            )
            if original_charge is None or Decimal(original_charge.amount) >= 0:
                return {
                    "operation_id": str(source.id),
                    "refunded_credits": "0",
                    "status": "no_charge",
                }
            existing_refund = await session.scalar(
                select(WalletTransaction).where(
                    WalletTransaction.reference_type == "generation_refund",
                    WalletTransaction.reference_id == str(source.id),
                    WalletTransaction.user_id == source.user_id,
                )
            )
            if existing_refund is not None:
                return {
                    "operation_id": str(source.id),
                    "transaction_id": str(existing_refund.id),
                    "refunded_credits": str(existing_refund.amount),
                    "status": "already_refunded",
                }
            amount = abs(Decimal(original_charge.amount))
            tx = await WalletService.credit(
                session,
                user_id=source.user_id,
                amount=amount,
                kind="generation_admin_refund",
                reference_type="generation_refund",
                reference_id=str(source.id),
                idempotency_key=f"admin-operation-refund:{source.id}",
            )
            return {
                "operation_id": str(source.id),
                "transaction_id": str(tx.id),
                "refunded_credits": str(tx.amount),
                "status": "refunded",
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="operations.refund",
            target_id=str(operation_id),
            request_payload=payload,
            operation=operation,
        )
