from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User


def _free_admin_telegram_ids() -> set[int]:
    result: set[int] = set()
    for raw in settings.admin_bootstrap_telegram_ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.add(int(raw))
        except ValueError:
            continue
    return result


class BillingPolicyService:
    @staticmethod
    async def user_has_free_bot_access(session: AsyncSession, user_id: uuid.UUID) -> bool:
        admin_ids = _free_admin_telegram_ids()
        if not admin_ids:
            return False
        telegram_id = await session.scalar(select(User.telegram_id).where(User.id == user_id))
        return telegram_id in admin_ids
