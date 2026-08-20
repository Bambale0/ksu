from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount


@dataclass(frozen=True, slots=True)
class BillingDecision:
    retail_cost: Decimal
    effective_cost: Decimal
    admin_free: bool


class BillingAccessService:
    """Resolve user-specific billing without weakening provider/resource safety.

    Every active AdminAccount is entitled to zero-cost product actions. The
    provider task still executes normally and all rate/concurrency/circuit gates
    remain in force; only ROXY wallet accounting is bypassed.
    """

    @staticmethod
    async def is_active_admin(session: AsyncSession, user_id: uuid.UUID) -> bool:
        admin_id = await session.scalar(
            select(AdminAccount.id).where(
                AdminAccount.user_id == user_id,
                AdminAccount.is_active.is_(True),
            )
        )
        return admin_id is not None

    @classmethod
    async def decision(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        retail_cost: Decimal | str | int | float,
    ) -> BillingDecision:
        retail = Decimal(str(retail_cost)).quantize(Decimal("0.01"))
        if retail < 0:
            raise ValueError("Retail cost must not be negative")
        admin_free = await cls.is_active_admin(session, user_id)
        return BillingDecision(
            retail_cost=retail,
            effective_cost=Decimal("0.00") if admin_free else retail,
            admin_free=admin_free,
        )
