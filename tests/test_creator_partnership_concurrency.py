from __future__ import annotations

import asyncio
import random
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.creator_partner_models import (
    CreatorPartnershipAgreement,
    CreatorPartnershipApplication,
    CreatorPartnershipGrant,
)
from app.db.models import AdminAccount, User, Wallet
from app.db.session import SessionFactory
from app.services.creator_partnership import (
    CreatorPartnershipConflict,
    CreatorPartnershipService,
    current_period,
)


def _telegram_id() -> int:
    return random.randint(9_910_000_000_000_000, 9_999_999_999_999_999)


@pytest.mark.asyncio
async def test_concurrent_creator_applications_leave_only_one_pending() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Concurrent creator")
        session.add(user)
        await session.commit()
        user_id = user.id

    async def submit(suffix: str) -> str:
        async with SessionFactory() as session:
            try:
                await CreatorPartnershipService.submit_application(
                    session,
                    user_id=user_id,
                    channel_name=f"Channel {suffix}",
                    channel_url=f"https://example.com/{suffix}",
                    audience_size=1000,
                    average_views=500,
                    cooperation_format="Reviews",
                    message="",
                    idempotency_key=f"creator-race-{user_id}-{suffix}",
                )
                await session.commit()
                return "created"
            except CreatorPartnershipConflict:
                await session.rollback()
                return "conflict"

    outcomes = await asyncio.gather(submit("a"), submit("b"))
    assert sorted(outcomes) == ["conflict", "created"]

    async with SessionFactory() as session:
        count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(CreatorPartnershipApplication)
                    .where(
                        CreatorPartnershipApplication.user_id == user_id,
                        CreatorPartnershipApplication.status == "pending",
                    )
                )
            )
            or 0
        )
        assert count == 1


@pytest.mark.asyncio
async def test_concurrent_monthly_grants_credit_wallet_once() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Grant creator")
        admin_user = User(telegram_id=_telegram_id(), first_name="Grant admin")
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        await session.flush()
        application = CreatorPartnershipApplication(
            user_id=user.id,
            idempotency_key=f"grant-race-app-{user.id}",
            channel_name="Grant channel",
            channel_url="https://example.com/grant",
            audience_size=1000,
            cooperation_format="Content",
            message="",
            status="approved",
            decided_by_admin_id=admin.id,
            decided_at=datetime.now(UTC),
        )
        session.add(application)
        await session.flush()
        agreement = CreatorPartnershipAgreement(
            application_id=application.id,
            user_id=user.id,
            status="active",
            terms_summary="Monthly grant",
            monthly_rox=Decimal("750"),
            terms={},
            starts_on=date.today().replace(day=1),
            approved_by_admin_id=admin.id,
            approved_at=datetime.now(UTC),
        )
        session.add(agreement)
        await session.commit()
        agreement_id = agreement.id
        user_id = user.id

    async def grant() -> bool:
        async with SessionFactory() as session:
            agreement = await session.get(CreatorPartnershipAgreement, agreement_id)
            assert agreement is not None
            _item, replayed = await CreatorPartnershipService.grant_agreement_period(
                session,
                agreement=agreement,
                period=current_period(),
                source="scheduler",
            )
            await session.commit()
            return replayed

    replay_flags = await asyncio.gather(grant(), grant())
    assert sorted(replay_flags) == [False, True]

    async with SessionFactory() as session:
        wallet = await session.get(Wallet, user_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("750.00")
        grants = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(CreatorPartnershipGrant)
                    .where(
                        CreatorPartnershipGrant.agreement_id == agreement_id,
                        CreatorPartnershipGrant.period == current_period(),
                    )
                )
            )
            or 0
        )
        assert grants == 1
