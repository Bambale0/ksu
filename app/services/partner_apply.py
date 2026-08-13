from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartnerWithdrawal
from app.services.partner import PartnerService
from app.services.partner_approval import PartnerApprovalService


class PartnerApplyService:
    @staticmethod
    async def create_withdrawal(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        requisites: str,
    ) -> PartnerWithdrawal:
        await PartnerApprovalService.require_approved(session, user_id=user_id)
        return await PartnerService.create_withdrawal(
            session,
            user_id=user_id,
            amount=amount,
            requisites=requisites,
        )
