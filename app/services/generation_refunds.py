from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WalletTransaction


async def existing_generation_refund(
    session: AsyncSession,
    *,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WalletTransaction | None:
    """Find either persisted refund shape while the caller holds the generation lock.

    The worker and admin action share one economic effect. Older admin refunds
    used a different reference type/key, so they must remain recognizable without
    rewriting the append-only wallet ledger.
    """
    return await session.scalar(
        select(WalletTransaction)
        .where(
            WalletTransaction.user_id == user_id,
            WalletTransaction.reference_id == str(generation_id),
            WalletTransaction.amount > 0,
            or_(
                and_(
                    WalletTransaction.reference_type == "generation",
                    WalletTransaction.kind == "generation_refund",
                ),
                and_(
                    WalletTransaction.reference_type == "generation_refund",
                    WalletTransaction.kind == "generation_admin_refund",
                ),
            ),
        )
        .order_by(WalletTransaction.created_at.asc(), WalletTransaction.id.asc())
        .limit(1)
    )
