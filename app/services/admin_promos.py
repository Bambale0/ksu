from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, PromoCode
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy


class AdminPromoService:
    @staticmethod
    async def list_promos(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        limit: int = 100,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "promocodes.read")
        rows = list(
            (
                await session.scalars(
                    select(PromoCode)
                    .order_by(PromoCode.created_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {"items": [AdminPromoService._view(item) for item in rows]}

    @staticmethod
    async def lookup(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        query: str,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "promocodes.read")
        raw = query.strip()
        promo = None
        try:
            promo_id = uuid.UUID(raw)
        except ValueError:
            promo_id = None
        if promo_id is not None:
            promo = await session.get(PromoCode, promo_id)
        if promo is None:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.code == raw.upper())
            )
        if promo is None:
            raise LookupError("Promo code not found")
        return AdminPromoService._view(promo)

    @staticmethod
    def _view(item: PromoCode) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "code": item.code,
            "reward_credits": str(item.reward_amount),
            "max_uses": item.max_uses,
            "uses_count": item.uses_count,
            "is_active": item.is_active,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        code: str,
        reward_credits: Decimal,
        max_uses: int | None,
        expires_at: datetime | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        normalized = code.strip().upper()
        if len(normalized) < 3 or len(normalized) > 64:
            raise ValueError("Promo code must contain 3..64 characters")
        if not all(char.isalnum() or char in {"_", "-"} for char in normalized):
            raise ValueError("Promo code contains unsupported characters")
        if reward_credits <= 0 or reward_credits > Decimal("100000"):
            raise ValueError("Invalid promo reward")
        if max_uses is not None and not 1 <= max_uses <= 10_000_000:
            raise ValueError("Invalid promo max_uses")
        payload = {
            "code": normalized,
            "reward_credits": str(reward_credits),
            "max_uses": max_uses,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        async def operation() -> dict[str, Any]:
            if await session.scalar(select(PromoCode).where(PromoCode.code == normalized)):
                raise ValueError("Promo code already exists")
            promo = PromoCode(
                code=normalized,
                reward_amount=reward_credits,
                max_uses=max_uses,
                is_active=True,
                expires_at=expires_at,
            )
            session.add(promo)
            await session.flush()
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=normalized,
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def set_active(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        promo_id: uuid.UUID,
        is_active: bool,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        payload = {"is_active": is_active}

        async def operation() -> dict[str, Any]:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
            )
            if promo is None:
                raise LookupError("Promo code not found")
            promo.is_active = is_active
            await session.flush()
            await session.refresh(promo)
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=str(promo_id),
            request_payload=payload,
            operation=operation,
        )
