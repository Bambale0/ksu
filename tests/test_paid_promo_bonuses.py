from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import (
    AdminAccount,
    Payment,
    PromoCode,
    PromoRedemption,
    User,
    Wallet,
    WalletTransaction,
)
from app.db.session import SessionFactory
from app.services.admin_promos import AdminPromoService
from app.services.payments import PaymentService
from app.services.promocodes import PromoCodeError, PromoCodeService


def _telegram_id() -> int:
    return 99_800_000_000_000 + random.randint(1, 999_999_999)


def _payment(*, user_id: uuid.UUID, amount: str = "300") -> Payment:
    return Payment(
        user_id=user_id,
        provider="yookassa",
        amount=Decimal(amount),
        currency="RUB",
        rox_amount=Decimal(amount),
        status="pending",
        payload={
            "package_id": f"p{amount}",
            "base_credits": amount,
            "bonus_credits": "0",
            "credited_credits": amount,
        },
    )


@pytest.mark.asyncio
async def test_promo_preview_never_credits_wallet() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Promo Preview")
        promo = PromoCode(
            code=f"PREVIEW{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("30"),
            max_uses=1000,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.commit()

        preview = await PromoCodeService.preview(
            session,
            user_id=user.id,
            code=promo.code.lower(),
        )

        assert preview.id == promo.id
        assert preview.reward_amount == Decimal("30")
        assert preview.uses_count == 0
        assert await session.get(Wallet, user.id) is None
        redemption = await session.scalar(
            select(PromoRedemption).where(PromoRedemption.user_id == user.id)
        )
        assert redemption is None


@pytest.mark.asyncio
async def test_promo_bonus_is_reserved_then_credited_only_after_successful_payment() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Promo Paid")
        promo = PromoCode(
            code=f"PAID{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("30"),
            max_uses=1000,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.flush()
        payment = _payment(user_id=user.id)
        session.add(payment)
        await session.commit()

        await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=promo.code,
        )
        await session.commit()

        redemption = await session.scalar(
            select(PromoRedemption).where(PromoRedemption.payment_id == payment.id)
        )
        assert redemption is not None
        assert redemption.status == "pending"
        assert promo.uses_count == 0
        assert await session.get(Wallet, user.id) is None
        assert payment.rox_amount == Decimal("300")
        assert payment.payload["promo_bonus_status"] == "reserved"
        assert payment.payload["bonus_credits"] == "30"
        assert payment.payload["credited_credits"] == "330"

        completed = await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )

        wallet = await session.get(Wallet, user.id)
        await session.refresh(promo)
        await session.refresh(redemption)
        assert wallet is not None
        assert wallet.balance == Decimal("330.00")
        assert completed.rox_amount == Decimal("300")
        assert completed.payload["promo_bonus_status"] == "applied"
        assert completed.payload["credited_credits"] == "330"
        assert promo.uses_count == 1
        assert redemption.status == "applied"
        assert redemption.redeemed_at is not None

        transactions = list(
            (
                await session.scalars(
                    select(WalletTransaction)
                    .where(WalletTransaction.user_id == user.id)
                    .order_by(WalletTransaction.created_at.asc(), WalletTransaction.id.asc())
                )
            ).all()
        )
        assert len(transactions) == 2
        assert {(row.kind, row.amount) for row in transactions} == {
            ("payment", Decimal("300.00")),
            ("promo_bonus", Decimal("30.00")),
        }

        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )
        await session.refresh(wallet)
        await session.refresh(promo)
        assert wallet.balance == Decimal("330.00")
        assert promo.uses_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("blocked_by", "expected_status"),
    [
        ("reservation_expired", "reservation_expired"),
        ("campaign_inactive", "inactive"),
        ("campaign_expired", "expired"),
    ],
)
async def test_reserved_promo_is_not_credited_after_shutdown(
    blocked_by: str,
    expected_status: str,
) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Promo Shutdown")
        promo = PromoCode(
            code=f"SHUT{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("30"),
            max_uses=1000,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.flush()
        payment = _payment(user_id=user.id)
        session.add(payment)
        await session.commit()

        await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=promo.code,
        )
        await session.commit()

        redemption = await session.scalar(
            select(PromoRedemption).where(PromoRedemption.payment_id == payment.id)
        )
        assert redemption is not None

        if blocked_by == "reservation_expired":
            redemption.reserved_until = datetime.now(UTC) - timedelta(seconds=1)
        elif blocked_by == "campaign_inactive":
            promo.is_active = False
        else:
            promo.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        completed = await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )

        wallet = await session.get(Wallet, user.id)
        await session.refresh(promo)
        await session.refresh(redemption)
        assert wallet is not None
        assert wallet.balance == Decimal("300.00")
        assert promo.uses_count == 0
        assert redemption.status == "released"
        assert completed.payload["promo_bonus_status"] == expected_status
        assert completed.payload["bonus_credits"] == "0"
        assert Decimal(str(completed.payload["credited_credits"])) == Decimal("300")


@pytest.mark.asyncio
async def test_pending_reservation_respects_campaign_limit_and_releases_on_failure() -> None:
    async with SessionFactory() as session:
        first = User(telegram_id=_telegram_id(), first_name="Promo First")
        second = User(telegram_id=_telegram_id(), first_name="Promo Second")
        promo = PromoCode(
            code=f"LIMIT{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("50"),
            max_uses=1,
            uses_count=0,
            is_active=True,
        )
        session.add_all([first, second, promo])
        await session.flush()
        first_payment = _payment(user_id=first.id, amount="500")
        second_payment = _payment(user_id=second.id, amount="500")
        session.add_all([first_payment, second_payment])
        await session.commit()

        await PromoCodeService.reserve_for_payment(
            session,
            payment=first_payment,
            code=promo.code,
        )
        await session.commit()

        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.preview(
                session,
                user_id=second.id,
                code=promo.code,
            )
        assert exc_info.value.code == "usage_limit_reached"

        await PromoCodeService.release_payment_reservation(
            session,
            payment=first_payment,
            reason="provider_failed",
        )
        assert first_payment.payload["promo_bonus_status"] == "released"
        assert first_payment.payload["bonus_credits"] == "0"
        assert Decimal(str(first_payment.payload["credited_credits"])) == Decimal("500")
        await session.commit()

        preview = await PromoCodeService.preview(
            session,
            user_id=second.id,
            code=promo.code,
        )
        assert preview.id == promo.id
        await PromoCodeService.reserve_for_payment(
            session,
            payment=second_payment,
            code=promo.code,
        )
        await session.commit()

        redemption = await session.scalar(
            select(PromoRedemption).where(PromoRedemption.payment_id == second_payment.id)
        )
        assert redemption is not None
        assert redemption.status == "pending"


@pytest.mark.asyncio
async def test_full_refund_reverses_paid_rox_and_promo_bonus() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Promo Refund")
        promo = PromoCode(
            code=f"REFUND{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("20"),
            max_uses=100,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.flush()
        payment = _payment(user_id=user.id, amount="100")
        session.add(payment)
        await session.commit()

        await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=promo.code,
        )
        await session.commit()
        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("120.00")

        refunded = await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("100"),
            provider="yookassa",
            idempotency_key=f"test-promo-refund:{payment.id}",
            reason="refund",
            provider_payload={"status": "refunded"},
        )

        await session.refresh(wallet)
        assert refunded.status == "refunded"
        assert wallet.balance == Decimal("0.00")
        assert refunded.payload["promo_bonus_reversed"] == "20"

@pytest.mark.asyncio
async def test_preview_rejects_live_reservation_but_same_payment_retry_stays_idempotent() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Promo Reserved")
        promo = PromoCode(
            code=f"RESERVED{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("25"),
            max_uses=2,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.flush()
        payment = _payment(user_id=user.id, amount="300")
        session.add(payment)
        await session.commit()

        first = await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=promo.code,
        )
        await session.commit()
        assert first is not None
        assert await PromoCodeService.remaining_uses(session, promo=promo) == 1

        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.preview(
                session,
                user_id=user.id,
                code=promo.code,
            )
        assert exc_info.value.code == "already_reserved"

        retried = await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=promo.code,
        )
        await session.commit()
        assert retried is not None
        assert retried.id == promo.id
        assert await PromoCodeService.remaining_uses(session, promo=promo) == 1

        redemptions = list(
            (
                await session.scalars(
                    select(PromoRedemption).where(
                        PromoRedemption.promo_id == promo.id,
                        PromoRedemption.user_id == user.id,
                    )
                )
            ).all()
        )
        assert len(redemptions) == 1
        assert redemptions[0].payment_id == payment.id
        assert redemptions[0].status == "pending"


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_oversubscribe_last_promo_slot() -> None:
    async with SessionFactory() as session:
        first = User(telegram_id=_telegram_id(), first_name="Promo Race First")
        second = User(telegram_id=_telegram_id(), first_name="Promo Race Second")
        promo = PromoCode(
            code=f"RACE{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("50"),
            max_uses=1,
            uses_count=0,
            is_active=True,
        )
        session.add_all([first, second, promo])
        await session.flush()
        first_payment = _payment(user_id=first.id, amount="500")
        second_payment = _payment(user_id=second.id, amount="500")
        session.add_all([first_payment, second_payment])
        await session.commit()
        promo_id = promo.id
        promo_code = promo.code
        payment_ids = (first_payment.id, second_payment.id)

    async def reserve(payment_id: uuid.UUID) -> str:
        async with SessionFactory() as worker:
            payment = await worker.get(Payment, payment_id)
            assert payment is not None
            try:
                await PromoCodeService.reserve_for_payment(
                    worker,
                    payment=payment,
                    code=promo_code,
                )
                await worker.commit()
                return "reserved"
            except PromoCodeError as exc:
                await worker.rollback()
                return exc.code

    outcomes = await asyncio.gather(*(reserve(payment_id) for payment_id in payment_ids))
    assert sorted(outcomes) == ["reserved", "usage_limit_reached"]

    async with SessionFactory() as session:
        promo = await session.get(PromoCode, promo_id)
        assert promo is not None
        assert promo.uses_count == 0
        assert await PromoCodeService.remaining_uses(session, promo=promo) == 0
        pending = int(
            (
                await session.scalar(
                    select(func.count(PromoRedemption.id)).where(
                        PromoRedemption.promo_id == promo_id,
                        PromoRedemption.status == "pending",
                    )
                )
            )
            or 0
        )
        assert pending == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires_at",
    [
        datetime.now(UTC) - timedelta(seconds=1),
        datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
    ],
)
async def test_admin_promo_rejects_past_or_timezone_less_expiration(
    expires_at: datetime,
) -> None:
    admin = AdminAccount(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="admin",
        permission_overrides={"allow": ["promocodes.manage"]},
        is_active=True,
    )
    async with SessionFactory() as session:
        with pytest.raises(ValueError):
            await AdminPromoService.create(
                session,
                admin=admin,
                code=f"INVALIDEXP{uuid.uuid4().hex[:8].upper()}",
                reward_credits=Decimal("10"),
                max_uses=100,
                expires_at=expires_at,
                idempotency_key=f"test-invalid-promo-expiry:{uuid.uuid4()}",
                request_id=f"test:{uuid.uuid4()}",
                confirmed=True,
            )

