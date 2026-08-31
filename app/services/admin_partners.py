from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, PartnerWithdrawal, ReferralRelation, ReferralReward, User
from app.db.payment_models import ReferralRewardReversal
from app.services.admin_commands import AdminCommandLedger, redact_secrets
from app.services.admin_policy import AdminPolicy
from app.services.partner_wallet import PartnerWalletTransferService


class AdminPartnerService:
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
        reversed_by_status = {
            state: Decimal(amount or 0)
            for state, amount in (
                await session.execute(
                    select(
                        ReferralReward.status,
                        func.coalesce(func.sum(ReferralRewardReversal.amount), 0),
                    )
                    .select_from(ReferralRewardReversal)
                    .join(ReferralReward, ReferralReward.id == ReferralRewardReversal.reward_id)
                    .group_by(ReferralReward.status)
                )
            ).all()
        }
        withdrawals = (
            await session.execute(
                select(
                    PartnerWithdrawal.status,
                    func.count(PartnerWithdrawal.id),
                    func.coalesce(func.sum(PartnerWithdrawal.amount), 0),
                ).group_by(PartnerWithdrawal.status)
            )
        ).all()
        reward_rows = []
        for state, count, gross_amount in rewards:
            gross = Decimal(gross_amount or 0)
            reversed_amount = reversed_by_status.get(state, Decimal("0"))
            reward_rows.append(
                {
                    "status": state,
                    "count": int(count or 0),
                    "amount": str(max(Decimal("0"), gross - reversed_amount)),
                    "gross_amount": str(gross),
                    "reversed_amount": str(reversed_amount),
                }
            )
        return {
            "referral_relations": referrals,
            "rewards": reward_rows,
            "withdrawals": [
                {"status": state, "count": int(count or 0), "amount": str(amount or 0)}
                for state, count, amount in withdrawals
            ],
        }

    @staticmethod
    def _withdrawal_view(item: PartnerWithdrawal, *, can_manage: bool) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "user_id": str(item.user_id),
            "amount": str(Decimal(item.amount)),
            "status": item.status,
            "requisites": redact_secrets(item.requisites) if can_manage else "[restricted]",
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
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
                AdminPartnerService._withdrawal_view(item, can_manage=can_manage)
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
        AdminPolicy.require_permission(admin, "partners.read")
        item = await session.get(PartnerWithdrawal, withdrawal_id)
        if item is None:
            raise LookupError("Withdrawal not found")
        return AdminPartnerService._withdrawal_view(
            item,
            can_manage=AdminPolicy.has_permission(admin, "partners.manage"),
        )

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
                user = await session.scalar(
                    select(User).where(User.id == withdrawal.user_id).with_for_update()
                )
                if user is None:
                    raise LookupError("Withdrawal user not found")
                accounting = await PartnerWalletTransferService.accounting(
                    session,
                    withdrawal.user_id,
                )
                committed = (
                    Decimal(accounting["reserved_or_paid"])
                    + Decimal(accounting["transferred_to_rox"])
                )
                if committed > Decimal(accounting["total_earned"]):
                    raise ValueError(
                        "Withdrawal is no longer backed by current partner earnings; reject or cancel it"
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
