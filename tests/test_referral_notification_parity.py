from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import (
    Notification,
    ReferralRelation,
    ReferralReward,
    User,
    WalletTransaction,
)
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.notification_events import register_notification_events

register_notification_events()


@pytest.mark.asyncio
async def test_new_referral_queues_partner_telegram_notification() -> None:
    async with SessionFactory() as session:
        inviter = User(
            telegram_id=980000000000101,
            username="creator",
            first_name="Creator",
        )
        referred = User(
            telegram_id=980000000000102,
            username="new_friend",
            first_name="Новый",
            last_name="Друг",
        )
        session.add_all([inviter, referred])
        await session.flush()

        session.add(
            ReferralRelation(
                referred_user_id=referred.id,
                inviter_user_id=inviter.id,
            )
        )
        await session.commit()

        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == inviter.id,
                Notification.kind == "referral_joined",
            )
        )
        assert notification is not None
        assert notification.title == "🎉 Новый реферал"
        assert "Новый Друг" in notification.body
        assert "@new_friend" in notification.body
        assert "ROX" in notification.body

        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        assert delivery.channel == "telegram"
        assert delivery.status == "pending"


@pytest.mark.asyncio
async def test_referral_payment_keeps_separate_partner_accrual_notification() -> None:
    async with SessionFactory() as session:
        partner = User(telegram_id=980000000000103, first_name="Partner")
        referred = User(telegram_id=980000000000104, first_name="Buyer")
        session.add_all([partner, referred])
        await session.flush()

        transaction = WalletTransaction(
            user_id=referred.id,
            kind="payment",
            amount=Decimal("500.00"),
            balance_before=Decimal("0.00"),
            balance_after=Decimal("500.00"),
            status="completed",
            idempotency_key="referral-notification-parity-payment",
        )
        session.add(transaction)
        await session.flush()

        session.add(
            ReferralReward(
                partner_user_id=partner.id,
                source_user_id=referred.id,
                source_transaction_id=transaction.id,
                level=1,
                percent=Decimal("10.00"),
                amount=Decimal("50.00"),
                status="available",
            )
        )
        await session.commit()

        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == partner.id,
                Notification.kind == "referral_line_1_topup",
            )
        )
        assert notification is not None
        assert "Buyer" in notification.body
        assert "500" in notification.body
        assert "+50" in notification.body

        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        assert delivery.status == "pending"
