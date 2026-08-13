from __future__ import annotations

import random
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.db.models import AdminAccount, PartnerWithdrawal, User
from app.db.partner_models import PartnerApplicationEvent
from app.db.session import SessionFactory
from app.services.partner import PartnerService
from app.services.partner_approval import PartnerApprovalRequired, PartnerApprovalService
from app.services.partner_decision import PartnerDecisionService


async def _actors(session):  # type: ignore[no-untyped-def]
    user = User(
        telegram_id=random.randint(6_000_000_000_000, 6_099_999_999_999),
        first_name="Partner applicant",
    )
    admin_user = User(
        telegram_id=random.randint(6_100_000_000_000, 6_199_999_999_999),
        first_name="Partner admin",
    )
    session.add_all([user, admin_user])
    await session.flush()
    admin = AdminAccount(
        user_id=admin_user.id,
        role="admin",
        permission_overrides={},
        is_active=True,
        mfa_enabled=True,
    )
    session.add(admin)
    await session.commit()
    return user, admin


@pytest.mark.asyncio
async def test_partner_submit_is_idempotent_and_rejected_can_resubmit() -> None:
    async with SessionFactory() as session:
        user, admin = await _actors(session)
        application, replayed = await PartnerApprovalService.submit(
            session,
            user_id=user.id,
            accepted=True,
        )
        await session.commit()
        application_id = application.id
        assert replayed is False
        assert application.status == "pending"

        again, replayed_again = await PartnerApprovalService.submit(
            session,
            user_id=user.id,
            accepted=True,
        )
        await session.commit()
        assert replayed_again is True
        assert again.id == application_id
        event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(PartnerApplicationEvent)
                .where(PartnerApplicationEvent.application_id == application_id)
            )
            or 0
        )
        assert event_count == 1

        rejected = await PartnerDecisionService.transition(
            session,
            user_id=user.id,
            admin=admin,
            target_status="rejected",
            reason="Need more information",
        )
        await session.commit()
        assert rejected.status == "rejected"

        resubmitted, replayed_resubmit = await PartnerApprovalService.submit(
            session,
            user_id=user.id,
            accepted=True,
        )
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
            await PartnerDecisionService.transition(
                session,
                user_id=user.id,
                admin=admin,
                target_status="suspended",
                reason="Invalid direct suspension",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_cash_withdrawal_requires_approved_partner(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionFactory() as session:
        user, admin = await _actors(session)
        monkeypatch.setattr(
            PartnerService,
            "_available_rewards",
            AsyncMock(return_value=Decimal("1000.00")),
        )
        await PartnerApprovalService.submit(session, user_id=user.id, accepted=True)
        await session.commit()

        with pytest.raises(PartnerApprovalRequired):
            await PartnerService.create_withdrawal(
                session,
                user=user,
                amount=Decimal("100.00"),
                requisites="test requisites",
            )
        await session.rollback()

        await PartnerDecisionService.transition(
            session,
            user_id=user.id,
            admin=admin,
            target_status="approved",
            reason="Application verified",
        )
        await session.commit()
        withdrawal = await PartnerService.create_withdrawal(
            session,
            user=user,
            amount=Decimal("100.00"),
            requisites="test requisites",
        )
        await session.commit()
        assert withdrawal.status == "pending"
        assert int(
            await session.scalar(
                select(func.count())
                .select_from(PartnerWithdrawal)
                .where(PartnerWithdrawal.user_id == user.id)
            )
            or 0
        ) == 1

        await PartnerDecisionService.transition(
            session,
            user_id=user.id,
            admin=admin,
            target_status="suspended",
            reason="Manual compliance suspension",
        )
        await session.commit()
        with pytest.raises(PartnerApprovalRequired):
            await PartnerService.create_withdrawal(
                session,
                user=user,
                amount=Decimal("50.00"),
                requisites="test requisites",
            )
