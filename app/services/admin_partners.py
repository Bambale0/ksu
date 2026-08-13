from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, PartnerWithdrawal, ReferralRelation, ReferralReward
from app.db.partner_models import PartnerApplication
from app.services.admin_commands import AdminCommandLedger, redact_secrets
from app.services.admin_policy import AdminPolicy
from app.services.partner_approval import PartnerApprovalService
from app.services.partner_decision import PartnerDecisionService


class AdminPartnerService:
    @staticmethod
    def application_view(item: PartnerApplication) -> dict[str, Any]:
        return {
            **PartnerApprovalService.public_view(item),
            "user_id": str(item.user_id),
            "application_data": item.application_data,
            "decided_by_admin_id": (
                str(item.decided_by_admin_id) if item.decided_by_admin_id else None
            ),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def list_applications(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "partners.read")
        stmt = select(PartnerApplication)
        if status:
            stmt = stmt.where(PartnerApplication.status == status)
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(PartnerApplication.updated_at.desc())
                    .offset(max(0, min(offset, 100_000)))
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        return {"items": [AdminPartnerService.application_view(item) for item in rows]}

    @staticmethod
    async def update_application(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        user_id: uuid.UUID,
        status: str,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "partners.manage",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        payload = {"status": status, "reason": reason}

        async def operation() -> dict[str, Any]:
            item = await PartnerDecisionService.transition(
                session,
                user_id=user_id,
                admin=admin,
                target_status=status,
                reason=reason,
            )
            return AdminPartnerService.application_view(item)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="partners.manage",
            target_id=str(user_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def analytics(session: AsyncSession, *, admin: AdminAccount) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "partners.read")
        referrals = int((await session.scalar(select(func.count()).select_from(ReferralRelation))) or 0)
        rewards = (
            await session.execute(
                select(
                    ReferralReward.status,
                    func.count(ReferralReward.id),
                    func.coalesce(func.sum(ReferralReward.amount), 0),
                ).group_by(ReferralReward.status)
            )
        ).all()
        withdrawals = (
            await session.execute(
                select(
                    PartnerWithdrawal.status,
                    func.count(PartnerWithdrawal.id),
                    func.coalesce(func.sum(PartnerWithdrawal.amount), 0),
                ).group_by(PartnerWithdrawal.status)
            )
        ).all()
        applications = (
            await session.execute(
                select(PartnerApplication.status, func.count(PartnerApplication.id)).group_by(
                    PartnerApplication.status
                )
            )
        ).all()
        return {
            "referral_relations": referrals,
            "rewards": [
                {"status": state, "count": int(count or 0), "amount": str(amount or 0)}
                for state, count, amount in rewards
            ],
            "withdrawals": [
                {"status": state, "count": int(count or 0), "amount": str(amount or 0)}
                for state, count, amount in withdrawals
            ],
            "applications": [
                {"status": state, "count": int(count or 0)} for state, count in applications
            ],
        }

    @staticmethod
    async def list_withdrawals(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "partners.read")
        stmt = select(PartnerWithdrawal)
        if status:
            stmt = stmt.where(PartnerWithdrawal.status == status)
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(PartnerWithdrawal.created_at.desc())
                    .offset(max(0, min(offset, 100_000)))
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        can_manage = AdminPolicy.has_permission(admin, "partners.manage")
        return {
            "items": [
                {
                    "id": str(item.id),
                    "user_id": str(item.user_id),
                    "amount": str(Decimal(item.amount)),
                    "status": item.status,
                    "requisites": redact_secrets(item.requisites) if can_manage else "[restricted]",
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in rows
            ]
        }

    @staticmethod
    async def withdrawal_detail(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        withdrawal_id: uuid.UUID,
    ) -> dict[str, Any]:
        result = await AdminPartnerService.list_withdrawals(
            session,
            admin=admin,
            limit=100,
            offset=0,
        )
        for item in result["items"]:
            if item["id"] == str(withdrawal_id):
                return item
        raise LookupError("Withdrawal not found")

    @staticmethod
    async def update_withdrawal(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        withdrawal_id: uuid.UUID,
        status: str,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "partners.withdrawal_manage",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        transitions = {
            "pending": {"processing", "rejected", "canceled"},
            "processing": {"paid", "rejected", "canceled"},
            "paid": set(),
            "rejected": set(),
            "canceled": set(),
        }
        payload = {"status": status, "reason": reason}

        async def operation() -> dict[str, Any]:
            withdrawal = await session.scalar(
                select(PartnerWithdrawal)
                .where(PartnerWithdrawal.id == withdrawal_id)
                .with_for_update()
            )
            if withdrawal is None:
                raise LookupError("Withdrawal not found")
            if status not in transitions.get(withdrawal.status, set()):
                raise ValueError(
                    f"Invalid withdrawal transition: {withdrawal.status} -> {status}"
                )
            if status in {"processing", "paid"}:
                await PartnerApprovalService.require_approved(
                    session,
                    user_id=withdrawal.user_id,
                )
            withdrawal.status = status
            await session.flush()
            return {
                "id": str(withdrawal.id),
                "status": withdrawal.status,
                "amount": str(withdrawal.amount),
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="partners.withdrawal_manage",
            target_id=str(withdrawal_id),
            request_payload=payload,
            operation=operation,
        )
