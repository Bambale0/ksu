from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.partner_models import PartnerApplication

TERMS_VERSION = "1"


class PartnerApprovalError(ValueError):
    pass


class PartnerApprovalRequired(PermissionError):
    pass


class PartnerApprovalService:
    @staticmethod
    async def get(session: AsyncSession, *, user_id: uuid.UUID, lock: bool = False) -> PartnerApplication | None:
        stmt = select(PartnerApplication).where(PartnerApplication.user_id == user_id)
        if lock:
            stmt = stmt.with_for_update()
        return await session.scalar(stmt)

    @staticmethod
    def public_view(application: PartnerApplication | None) -> dict[str, Any]:
        if application is None:
            return {"status": "not_applied", "terms_version": TERMS_VERSION, "can_apply": True, "can_withdraw": False}
        return {
            "id": str(application.id),
            "status": application.status,
            "terms_version": application.terms_version,
            "can_apply": application.status == "rejected",
            "can_withdraw": application.status == "approved",
            "decision_reason": application.decision_reason,
            "submitted_at": application.submitted_at.isoformat(),
            "decided_at": application.decided_at.isoformat() if application.decided_at else None,
        }
