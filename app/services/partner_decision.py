from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount
from app.db.partner_models import PartnerApplicationEvent
from app.services.partner_approval import PartnerApprovalError, PartnerApprovalService

ALLOWED = {
    "pending": {"approved", "rejected"},
    "approved": {"suspended"},
    "suspended": {"approved", "rejected"},
    "rejected": set(),
}


class PartnerDecisionService:
    @staticmethod
    def validate(current: str, target: str) -> None:
        if target not in ALLOWED.get(current, set()):
            raise PartnerApprovalError(f"Invalid partner transition: {current} -> {target}")

    @classmethod
    async def transition(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        admin: AdminAccount,
        target_status: str,
        reason: str,
    ):
        application = await PartnerApprovalService.get(session, user_id=user_id, lock=True)
        if application is None:
            raise LookupError("Partner application not found")
        target = target_status.strip().lower()
        cls.validate(application.status, target)
        clean_reason = reason.strip()
        if len(clean_reason) < 3 or len(clean_reason) > 1000:
            raise PartnerApprovalError("Decision reason must contain 3..1000 characters")
        previous = application.status
        application.status = target
        application.decided_at = datetime.now(UTC)
        application.decided_by_admin_id = admin.id
        application.decision_reason = clean_reason
        session.add(
            PartnerApplicationEvent(
                application_id=application.id,
                user_id=user_id,
                from_status=previous,
                to_status=target,
                actor_type="admin",
                actor_admin_id=admin.id,
                reason=clean_reason,
                metadata_json={},
            )
        )
        await session.flush()
        return application
