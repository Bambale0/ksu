from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.partner_models import PartnerApplication, PartnerApplicationEvent

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

    @classmethod
    async def submit(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        accepted: bool,
    ) -> tuple[PartnerApplication, bool]:
        if not accepted:
            raise PartnerApprovalError("Partner terms must be accepted")
        application = await cls.get(session, user_id=user_id, lock=True)
        if application is not None and application.status == "pending":
            return application, True
        previous = application.status if application is not None else None
        if previous not in {None, "rejected"}:
            raise PartnerApprovalError(f"Cannot apply from {previous}")
        now = datetime.now(UTC)
        if application is None:
            application = PartnerApplication(
                user_id=user_id,
                status="pending",
                terms_version=TERMS_VERSION,
                agreed_at=now,
                submitted_at=now,
                application_data={},
            )
            session.add(application)
            await session.flush()
        else:
            application.status = "pending"
            application.terms_version = TERMS_VERSION
            application.agreed_at = now
            application.submitted_at = now
            application.decided_at = None
            application.decided_by_admin_id = None
            application.decision_reason = None
        session.add(
            PartnerApplicationEvent(
                application_id=application.id,
                user_id=user_id,
                from_status=previous,
                to_status="pending",
                actor_type="user",
                actor_user_id=user_id,
                reason="terms_accepted",
                metadata_json={"terms_version": TERMS_VERSION},
            )
        )
        await session.flush()
        return application, False

    @classmethod
    async def require_approved(cls, session: AsyncSession, *, user_id: uuid.UUID) -> PartnerApplication:
        application = await cls.get(session, user_id=user_id, lock=True)
        if application is None or application.status != "approved":
            current = application.status if application is not None else "not_applied"
            raise PartnerApprovalRequired(f"Cash withdrawals require approved partner status; current status: {current}")
        return application
