from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Generation,
    PartnerWithdrawal,
    Payment,
    SupportTicket,
    User,
    WalletTransaction,
)
from app.services.admin_commands import redact_secrets
from app.services.admin_policy import AdminPolicy


class AdminReportingService:
    @staticmethod
    async def summary(session: AsyncSession, *, admin: Any) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "dashboard.read")
        total_users = int((await session.scalar(select(func.count()).select_from(User))) or 0)
        active_users = int(
            (
                await session.scalar(
                    select(func.count()).select_from(User).where(User.is_active.is_(True))
                )
            )
            or 0
        )
        active_generations = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(Generation)
                    .where(Generation.status.in_(["queued", "submitting", "generating", "retry"]))
                )
            )
            or 0
        )
        failed_generations = int(
            (
                await session.scalar(
                    select(func.count()).select_from(Generation).where(Generation.status == "failed")
                )
            )
            or 0
        )
        open_tickets = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(SupportTicket.status.in_(["open", "in_progress"]))
                )
            )
            or 0
        )
        pending_withdrawals = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(PartnerWithdrawal)
                    .where(PartnerWithdrawal.status.in_(["pending", "processing"]))
                )
            )
            or 0
        )
        payment_row = (
            await session.execute(
                select(
                    func.count(Payment.id),
                    func.coalesce(func.sum(Payment.amount), 0),
                    func.coalesce(func.sum(Payment.rox_amount), 0),
                ).where(Payment.status == "succeeded")
            )
        ).one()
        return {
            "users": {"total": total_users, "active": active_users},
            "generations": {"active": active_generations, "failed": failed_generations},
            "support": {"open": open_tickets},
            "withdrawals": {"pending_or_processing": pending_withdrawals},
            "payments": {
                "succeeded": int(payment_row[0] or 0),
                "amount": str(payment_row[1] or 0),
                "credits": str(payment_row[2] or 0),
            },
        }

    @staticmethod
    async def generations(
        session: AsyncSession,
        *,
        admin: Any,
        status: str | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "generations.read")
        stmt = select(Generation)
        count_stmt = select(func.count()).select_from(Generation)
        conditions = []
        if status:
            conditions.append(Generation.status == status)
        if user_id:
            conditions.append(Generation.user_id == user_id)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        bounded_limit = max(1, min(limit, 100))
        bounded_offset = max(0, min(offset, 100_000))
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(Generation.created_at.desc())
                    .offset(bounded_offset)
                    .limit(bounded_limit)
                )
            ).all()
        )
        return {
            "items": [
                {
                    "id": str(item.id),
                    "user_id": str(item.user_id),
                    "kind": item.kind,
                    "model_id": (item.parameters or {}).get("_model_id"),
                    "status": item.status,
                    "provider": item.provider,
                    "external_id": item.external_id,
                    "cost_credits": str(item.cost_rox),
                    "prompt": item.prompt[:1000],
                    "input_url": item.input_url,
                    "result_url": item.result_url,
                    "error": item.error[:1000] if item.error else None,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in rows
            ],
            "total": int((await session.scalar(count_stmt)) or 0),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @staticmethod
    async def payments(
        session: AsyncSession,
        *,
        admin: Any,
        status: str | None = None,
        provider: str | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "payments.read")
        stmt = select(Payment)
        count_stmt = select(func.count()).select_from(Payment)
        conditions = []
        if status:
            conditions.append(Payment.status == status)
        if provider:
            conditions.append(Payment.provider == provider)
        if user_id:
            conditions.append(Payment.user_id == user_id)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        bounded_limit = max(1, min(limit, 100))
        bounded_offset = max(0, min(offset, 100_000))
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(Payment.created_at.desc())
                    .offset(bounded_offset)
                    .limit(bounded_limit)
                )
            ).all()
        )
        return {
            "items": [AdminReportingService.payment_view(item) for item in rows],
            "total": int((await session.scalar(count_stmt)) or 0),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @staticmethod
    def payment_view(payment: Payment) -> dict[str, Any]:
        return {
            "id": str(payment.id),
            "user_id": str(payment.user_id),
            "provider": payment.provider,
            "external_id": payment.external_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "credits": str(payment.rox_amount),
            "status": payment.status,
            "payload": redact_secrets(payment.payload or {}),
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat(),
        }

    @staticmethod
    async def finance(session: AsyncSession, *, admin: Any) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "finance.read")
        payment_rows = (
            await session.execute(
                select(
                    Payment.currency,
                    Payment.status,
                    func.count(Payment.id),
                    func.coalesce(func.sum(Payment.amount), 0),
                    func.coalesce(func.sum(Payment.rox_amount), 0),
                ).group_by(Payment.currency, Payment.status)
            )
        ).all()
        withdrawal_rows = (
            await session.execute(
                select(
                    PartnerWithdrawal.status,
                    func.count(PartnerWithdrawal.id),
                    func.coalesce(func.sum(PartnerWithdrawal.amount), 0),
                ).group_by(PartnerWithdrawal.status)
            )
        ).all()
        wallet_totals = (
            await session.execute(
                select(
                    func.coalesce(func.sum(WalletTransaction.amount), 0),
                    func.count(WalletTransaction.id),
                )
            )
        ).one()
        return {
            "payments": [
                {
                    "currency": currency,
                    "status": status,
                    "count": int(count or 0),
                    "amount": str(Decimal(amount or 0)),
                    "credits": str(Decimal(credits or 0)),
                }
                for currency, status, count, amount, credits in payment_rows
            ],
            "withdrawals": [
                {"status": status, "count": int(count or 0), "amount": str(amount or 0)}
                for status, count, amount in withdrawal_rows
            ],
            "wallet": {
                "net_credits": str(wallet_totals[0] or 0),
                "transactions": int(wallet_totals[1] or 0),
            },
        }
