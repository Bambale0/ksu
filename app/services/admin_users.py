from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdminAccount,
    AdminSession,
    Generation,
    Payment,
    SupportTicket,
    User,
    Wallet,
)
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.admin_security import AdminAuditService
from app.services.credits import InternalCreditService
from app.services.wallet import WalletService


class AdminUserNotFound(LookupError):
    pass


class AdminUserConflict(RuntimeError):
    pass


class AdminUserService:
    @staticmethod
    def _masked_telegram_id(value: int) -> str:
        text = str(value)
        return "****" if len(text) <= 4 else f"***{text[-4:]}"

    @classmethod
    def _view(
        cls,
        user: User,
        *,
        balance: Decimal | None,
        can_view_pii: bool,
    ) -> dict[str, Any]:
        credits = Decimal(balance or Decimal("0"))
        return {
            "id": str(user.id),
            "username": user.username if can_view_pii else None,
            "first_name": user.first_name if can_view_pii else "[restricted]",
            "last_name": user.last_name if can_view_pii else None,
            "telegram_id": (
                user.telegram_id
                if can_view_pii
                else cls._masked_telegram_id(user.telegram_id)
            ),
            "is_active": user.is_active,
            "balance_credits": str(credits),
            "balance_rub": str(InternalCreditService.rubles_for(credits)),
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
        }

    @classmethod
    async def list_users(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        q: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "users.read")
        can_pii = AdminPolicy.has_permission(admin, "users.pii")
        stmt = select(User, Wallet.balance).outerjoin(Wallet, Wallet.user_id == User.id)
        count_stmt = select(func.count()).select_from(User)
        conditions = []
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if q:
            search = q.strip()
            text_condition = or_(
                User.username.ilike(f"%{search}%"),
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
            )
            if search.isdigit():
                text_condition = or_(text_condition, User.telegram_id == int(search))
            try:
                internal_id = uuid.UUID(search)
            except ValueError:
                internal_id = None
            if internal_id is not None:
                text_condition = or_(text_condition, User.id == internal_id)
            conditions.append(text_condition)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        bounded_limit = max(1, min(limit, 100))
        bounded_offset = max(0, min(offset, 100_000))
        rows = (
            await session.execute(
                stmt.order_by(User.created_at.desc())
                .offset(bounded_offset)
                .limit(bounded_limit)
            )
        ).all()
        total = int((await session.scalar(count_stmt)) or 0)
        return {
            "items": [
                cls._view(user, balance=balance, can_view_pii=can_pii)
                for user, balance in rows
            ],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @classmethod
    async def get_user(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "users.read")
        user = await session.get(User, user_id)
        if user is None:
            raise AdminUserNotFound("User not found")
        wallet = await session.get(Wallet, user_id)
        result = cls._view(
            user,
            balance=Decimal(wallet.balance) if wallet else Decimal("0"),
            can_view_pii=AdminPolicy.has_permission(admin, "users.pii"),
        )
        result["stats"] = {
            "generations": int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(Generation)
                        .where(Generation.user_id == user_id)
                    )
                )
                or 0
            ),
            "payments": int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(Payment)
                        .where(Payment.user_id == user_id)
                    )
                )
                or 0
            ),
            "support_tickets": int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(SupportTicket)
                        .where(SupportTicket.user_id == user_id)
                    )
                )
                or 0
            ),
        }
        admin_account = await session.scalar(
            select(AdminAccount).where(AdminAccount.user_id == user_id)
        )
        result["is_admin"] = bool(admin_account and admin_account.is_active)
        return result

    @classmethod
    async def set_blocked(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        user_id: uuid.UUID,
        blocked: bool,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        action = "users.block" if blocked else "users.unblock"
        AdminPolicy.authorize_action(
            admin,
            action,
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        payload = {"blocked": blocked, "reason": reason}

        async def operation() -> dict[str, Any]:
            user = await session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                raise AdminUserNotFound("User not found")
            target_admin = await session.scalar(
                select(AdminAccount).where(AdminAccount.user_id == user_id)
            )
            if blocked and target_admin is not None and target_admin.is_active:
                if admin.role != "owner":
                    raise AdminPolicyError("Only owner may block an admin user")
                if target_admin.id == admin.id:
                    raise AdminUserConflict("Cannot block your own owner user")
            before = user.is_active
            user.is_active = not blocked
            await AdminAuditService.record(
                session,
                action=f"admin.user.{'blocked' if blocked else 'unblocked'}",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="user",
                resource_id=str(user.id),
                reason=reason,
                metadata={"before": before, "after": user.is_active},
            )
            return {"id": str(user.id), "is_active": user.is_active}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action=action,
            target_id=str(user_id),
            request_payload=payload,
            operation=operation,
        )

    @classmethod
    async def adjust_balance(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        user_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "users.balance_adjust",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        if amount == 0:
            raise ValueError("Adjustment amount cannot be zero")
        if abs(amount) > Decimal("100000"):
            raise ValueError("Adjustment exceeds safety limit")
        payload = {"amount": str(amount), "reason": reason}

        async def operation() -> dict[str, Any]:
            user = await session.get(User, user_id)
            if user is None:
                raise AdminUserNotFound("User not found")
            wallet_key = f"admin-command:{idempotency_key}"
            if amount > 0:
                tx = await WalletService.credit(
                    session,
                    user_id=user.id,
                    amount=amount,
                    kind="admin_adjustment",
                    reference_type="admin",
                    reference_id=str(admin.id),
                    idempotency_key=wallet_key,
                )
            else:
                tx = await WalletService.debit(
                    session,
                    user_id=user.id,
                    amount=abs(amount),
                    kind="admin_adjustment",
                    reference_type="admin",
                    reference_id=str(admin.id),
                    idempotency_key=wallet_key,
                )
            await AdminAuditService.record(
                session,
                action="admin.wallet.adjusted",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="user",
                resource_id=str(user.id),
                reason=reason,
                metadata={
                    "transaction_id": str(tx.id),
                    "amount_credits": str(amount),
                    "balance_before": str(tx.balance_before),
                    "balance_after": str(tx.balance_after),
                },
            )
            return {
                "transaction_id": str(tx.id),
                "balance_before": str(tx.balance_before),
                "balance_after": str(tx.balance_after),
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="users.balance_adjust",
            target_id=str(user_id),
            request_payload=payload,
            operation=operation,
        )
