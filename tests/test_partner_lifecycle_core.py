from __future__ import annotations

import random

import pytest
from sqlalchemy import func, select

from app.db.models import AdminAccount, User
from app.db.partner_models import PartnerApplicationEvent
from app.db.session import SessionFactory
from app.services.partner_approval import PartnerApprovalService
from app.services.partner_decision import PartnerDecisionService


async def _actors(session):  # type: ignore[no-untyped-def]
    user = User(telegram_id=random.randint(6_000_000_000_000, 6_099_999_999_999), first_name="Partner applicant")
    admin_user = User(telegram_id=random.randint(6_100_000_000_000, 6_199_999_999_999), first_name="Partner admin")
    session.add_all([user, admin_user])
    await session.flush()
    admin = AdminAccount(user_id=admin_user.id, role="admin", permission_overrides={}, is_active=True, mfa_enabled=True)
    session.add(admin)
    await session.commit()
    return user, admin


@pytest.mark.asyncio
async def test_partner_submit_is_idempotent_and_rejected_can_resubmit() -> None:
    async with SessionFactory() as session:
        user, admin = await _actors(session)
        application, replayed = await PartnerApprovalService.submit(session, user_id=user.id, accepted=True)
        await session.commit()
        application_id = application.id
        assert replayed is False
        again, replayed_again = await PartnerApprovalService.submit(session, user_id=user.id, accepted=True)
        await session.commit()
        assert replayed_again is True
        assert again.id == application_id
        assert int(await session.scalar(select(func.count()).select_from(PartnerApplicationEvent).where(PartnerApplicationEvent.application_id == application_id)) or 0) == 1
        rejected = await PartnerDecisionService.transition(session, user_id=user.id, admin=admin, target_status="rejected", reason="Need more information")
        await session.commit()
        assert rejected.status == "rejected"
        resubmitted, replayed_resubmit = await PartnerApprovalService.submit(session, user_id=user.id, accepted=True)
        await session.commit()
        assert replayed_resubmit is False
        assert resubmitted.status == "pending"


@pytest.mark.asyncio
async def test_invalid_partner_transition_is_rejected() -> None:
    async with SessionFactory() as session:
        user, admin = await _actors(session)
        await PartnerApprovalService.submit(session, user_id=user.id, accepted=True)
        await session.commit()
        with pytest.raises(ValueError):
            await PartnerDecisionService.transition(session, user_id=user.id, admin=admin, target_status="suspended", reason="Invalid direct suspension")
