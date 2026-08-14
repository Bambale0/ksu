import random
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.creator_partner_models import (
    CreatorPartnershipAgreement,
    CreatorPartnershipApplication,
)
from app.db.models import AdminAccount, ReferralReward, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.creator_partnership import (
    CreatorPartnershipConflict,
    CreatorPartnershipService,
    current_period,
)


def _telegram_id() -> int:
    return random.randint(9_810_000_000_000_000, 9_899_999_999_999_999)


@pytest.mark.asyncio
async def test_creator_application_is_idempotent_and_only_one_pending() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add(user)
        await session.flush()

        first, replayed = await CreatorPartnershipService.submit_application(
            session,
            user_id=user.id,
            channel_name="Creator Channel",
            channel_url="https://t.me/creator_channel",
            audience_size=2500,
            average_views=1400,
            cooperation_format="Интеграции",
            message="Готов делать обзоры",
            idempotency_key=f"creator-application:{user.id}",
        )
        second, replayed_second = await CreatorPartnershipService.submit_application(
            session,
            user_id=user.id,
            channel_name="Creator Channel",
            channel_url="https://t.me/creator_channel",
            audience_size=2500,
            average_views=1400,
            cooperation_format="Интеграции",
            message="Готов делать обзоры",
            idempotency_key=f"creator-application:{user.id}",
        )
        assert not replayed
        assert replayed_second
        assert first.id == second.id

        with pytest.raises(CreatorPartnershipConflict):
            await CreatorPartnershipService.submit_application(
                session,
                user_id=user.id,
                channel_name="Second",
                channel_url="https://example.com/channel",
                audience_size=3000,
                average_views=None,
                cooperation_format="Амбассадор",
                message="",
                idempotency_key=f"creator-application-2:{user.id}",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_monthly_creator_grant_is_spend_only_and_idempotent() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Partner")
        admin_user = User(telegram_id=_telegram_id(), first_name="Admin")
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        await session.flush()
        application = CreatorPartnershipApplication(
            user_id=user.id,
            idempotency_key=f"approved:{user.id}",
            channel_name="Channel",
            channel_url="https://t.me/channel",
            audience_size=10_000,
            average_views=5000,
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
            terms_summary="4 публикации в месяц",
            monthly_rox=Decimal("750"),
            terms={"posts": 4},
            starts_on=date.today().replace(day=1),
            approved_by_admin_id=admin.id,
            approved_at=datetime.now(UTC),
        )
        session.add(agreement)
        await session.flush()

        grant, replayed = await CreatorPartnershipService.grant_agreement_period(
            session,
            agreement=agreement,
            period=current_period(),
            source="scheduler",
        )
        same, replayed_same = await CreatorPartnershipService.grant_agreement_period(
            session,
            agreement=agreement,
            period=current_period(),
            source="scheduler",
        )
        await session.commit()

        assert not replayed
        assert replayed_same
        assert grant.id == same.id
        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("750.00")
        txs = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.user_id == user.id,
                        WalletTransaction.kind == "creator_monthly_grant",
                    )
                )
            ).all()
        )
        assert len(txs) == 1
        assert txs[0].amount == Decimal("750.00")
        referral_count = await session.scalar(
            select(func.count()).select_from(ReferralReward).where(
                ReferralReward.partner_user_id == user.id
            )
        )
        assert int(referral_count or 0) == 0


@pytest.mark.asyncio
async def test_paused_creator_agreement_cannot_mint_grant() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Paused")
        admin_user = User(telegram_id=_telegram_id(), first_name="Admin")
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        await session.flush()
        application = CreatorPartnershipApplication(
            user_id=user.id,
            idempotency_key=f"paused:{user.id}",
            channel_name="Paused Channel",
            channel_url="https://example.com/channel",
            audience_size=500,
            cooperation_format="Reviews",
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
            status="paused",
            terms_summary="Paused",
            monthly_rox=Decimal("100"),
            terms={},
            starts_on=date.today().replace(day=1),
            approved_by_admin_id=admin.id,
            approved_at=datetime.now(UTC),
        )
        session.add(agreement)
        await session.flush()
        with pytest.raises(CreatorPartnershipConflict):
            await CreatorPartnershipService.grant_agreement_period(
                session,
                agreement=agreement,
                period=current_period(),
                source="scheduler",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_creator_status_exposes_agreement_and_grant_history() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Status")
        admin_user = User(telegram_id=_telegram_id(), first_name="Admin")
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        await session.flush()
        application = CreatorPartnershipApplication(
            user_id=user.id,
            idempotency_key=f"status:{user.id}",
            channel_name="Status Channel",
            channel_url="https://example.com/status",
            audience_size=7000,
            cooperation_format="Ambassador",
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
            terms_summary="Personal terms",
            monthly_rox=Decimal("500"),
            terms={},
            starts_on=date.today().replace(day=1),
            approved_by_admin_id=admin.id,
            approved_at=datetime.now(UTC),
        )
        session.add(agreement)
        await session.flush()
        await CreatorPartnershipService.grant_agreement_period(
            session,
            agreement=agreement,
            period=current_period(),
            source="scheduler",
        )
        await session.commit()

        payload = await CreatorPartnershipService.status(session, user_id=user.id)
        assert payload["application"]["status"] == "approved"
        assert payload["agreement"]["status"] == "active"
        assert payload["agreement"]["monthly_rox"] == "500.00"
        assert payload["total_granted_rox"] == "500.00"
        assert len(payload["grants"]) == 1
