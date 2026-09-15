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
    ReferralRelation,
    ReferralReward,
    User,
    Wallet,
    WalletTransaction,
)
from app.db.session import SessionFactory
from app.services.admin_promos import AdminPromoService
from app.services.partner_promo_program import PartnerPromoProgramService
from app.services.payments import PaymentService
from app.services.promocodes import PromoCodeError, PromoCodeService
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


def _telegram_id() -> int:
    return 99_800_000_000_000 + random.randint(1, 999_999_999)


async def _user(session, name: str) -> User:
    user = User(telegram_id=_telegram_id(), first_name=name)
    session.add(user)
    await session.flush()
    return user


async def _promo(session, *, partner: User, max_uses: int | None = 100) -> PromoCode:
    config = await PartnerPromoProgramService.get_config(session)
    promo = PromoCode(
        code=f"PARTNER{uuid.uuid4().hex[:8].upper()}",
        reward_amount=Decimal(config.welcome_rox),
        partner_user_id=partner.id,
        max_uses=max_uses,
        uses_count=0,
        is_active=True,
    )
    session.add(promo)
    await session.flush()
    return promo


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
async def test_partner_promo_activation_credits_welcome_once_and_sets_attribution() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Partner")
        user = await _user(session, "Promo user")
        promo = await _promo(session, partner=partner)
        config = await PartnerPromoProgramService.get_config(session)
        await session.commit()

        first = await PromoCodeService.activate(session, user_id=user.id, code=promo.code.lower())
        await session.commit()
        second = await PromoCodeService.activate(session, user_id=user.id, code=promo.code)
        await session.commit()

        wallet = await session.get(Wallet, user.id)
        relation = await session.get(ReferralRelation, user.id)
        await session.refresh(promo)
        redemption = await session.scalar(
            select(PromoRedemption).where(
                PromoRedemption.user_id == user.id,
                PromoRedemption.promo_id == promo.id,
            )
        )
        transactions = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.user_id == user.id,
                        WalletTransaction.kind == "partner_promo_welcome",
                    )
                )
            ).all()
        )

        assert first.activated is True
        assert second.activated is False
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal(config.welcome_rox)
        assert relation is not None
        assert relation.inviter_user_id == partner.id
        assert relation.source == "promo"
        assert relation.promo_id == promo.id
        assert promo.uses_count == 1
        assert redemption is not None and redemption.status == "applied"
        assert len(transactions) == 1


@pytest.mark.asyncio
async def test_same_partner_link_is_upgraded_but_other_partner_cannot_steal_attribution() -> None:
    async with SessionFactory() as session:
        first_partner = await _user(session, "First partner")
        second_partner = await _user(session, "Second partner")
        upgrade_user = await _user(session, "Upgrade user")
        locked_user = await _user(session, "Locked user")
        first_promo = await _promo(session, partner=first_partner)
        second_promo = await _promo(session, partner=second_partner)
        session.add_all(
            [
                ReferralRelation(
                    referred_user_id=upgrade_user.id,
                    inviter_user_id=first_partner.id,
                    source="link",
                ),
                ReferralRelation(
                    referred_user_id=locked_user.id,
                    inviter_user_id=second_partner.id,
                    source="link",
                ),
            ]
        )
        await session.commit()

        activation = await PromoCodeService.activate(
            session,
            user_id=upgrade_user.id,
            code=first_promo.code,
        )
        await session.commit()
        assert activation.activated is True
        upgraded = await session.get(ReferralRelation, upgrade_user.id)
        assert upgraded is not None
        assert upgraded.source == "promo"
        assert upgraded.promo_id == first_promo.id

        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.activate(
                session,
                user_id=locked_user.id,
                code=first_promo.code,
            )
        await session.rollback()
        assert exc_info.value.code == "already_attributed"
        locked = await session.get(ReferralRelation, locked_user.id)
        assert locked is not None
        assert locked.inviter_user_id == second_partner.id
        assert locked.source == "link"


@pytest.mark.asyncio
async def test_concurrent_activation_cannot_oversubscribe_last_promo_slot() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Race partner")
        first = await _user(session, "Race first")
        second = await _user(session, "Race second")
        promo = await _promo(session, partner=partner, max_uses=1)
        await session.commit()
        promo_id = promo.id
        promo_code = promo.code
        user_ids = (first.id, second.id)

    async def activate(user_id: uuid.UUID) -> str:
        async with SessionFactory() as worker:
            try:
                await PromoCodeService.activate(worker, user_id=user_id, code=promo_code)
                await worker.commit()
                return "activated"
            except PromoCodeError as exc:
                await worker.rollback()
                return exc.code

    outcomes = await asyncio.gather(*(activate(user_id) for user_id in user_ids))
    assert sorted(outcomes) == ["activated", "usage_limit_reached"]

    async with SessionFactory() as session:
        promo = await session.get(PromoCode, promo_id)
        assert promo is not None
        assert promo.uses_count == 1
        assert int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(PromoRedemption)
                    .where(
                        PromoRedemption.promo_id == promo_id,
                        PromoRedemption.status == "applied",
                    )
                )
            )
            or 0
        ) == 1


@pytest.mark.asyncio
async def test_partner_promo_payment_keeps_package_exact_and_pays_first_line_only() -> None:
    async with SessionFactory() as session:
        second_line = await _user(session, "Second line")
        partner = await _user(session, "Partner")
        buyer = await _user(session, "Buyer")
        promo = await _promo(session, partner=partner)
        session.add(
            ReferralRelation(
                referred_user_id=partner.id,
                inviter_user_id=second_line.id,
                source="link",
            )
        )
        payment = _payment(user_id=buyer.id)
        session.add(payment)
        await session.commit()

        await PromoCodeService.reserve_for_payment(session, payment=payment, code=promo.code)
        await session.commit()

        # Promo activation is separate from checkout economics.
        assert payment.payload["bonus_credits"] == "0"
        assert Decimal(str(payment.payload["credited_credits"])) == Decimal("300")
        assert payment.payload["promo_bonus_status"] == "activated"

        completed = await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )

        buyer_wallet = await session.get(Wallet, buyer.id)
        partner_wallet = await session.get(Wallet, partner.id)
        config = await PartnerPromoProgramService.get_config(session)
        rewards = list(
            (
                await session.scalars(
                    select(ReferralReward)
                    .where(ReferralReward.source_user_id == buyer.id)
                    .order_by(ReferralReward.level)
                )
            ).all()
        )

        assert completed.rox_amount == Decimal("300")
        assert completed.payload["bonus_credits"] == "0"
        assert buyer_wallet is not None
        assert Decimal(buyer_wallet.balance) == Decimal("300") + Decimal(config.welcome_rox)
        assert partner_wallet is not None
        assert Decimal(partner_wallet.balance) == Decimal(config.topup_partner_rox)
        assert [(row.level, Decimal(row.percent), Decimal(row.amount)) for row in rewards] == [
            (1, Decimal(config.first_line_percent), Decimal("90.00")),
        ]
        assert (await ReferralService.stats(session, second_line.id))["available"] == Decimal("0")

        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("300"),
            provider="yookassa",
            idempotency_key=f"partner-promo-refund:{payment.id}",
            reason="refund",
            provider_payload={"status": "refunded"},
        )
        await session.refresh(buyer_wallet)
        await session.refresh(partner_wallet)
        assert Decimal(buyer_wallet.balance) == Decimal(config.welcome_rox)
        assert Decimal(partner_wallet.balance) == Decimal("0")
        assert (await ReferralService.stats(session, partner.id))["available"] == Decimal("0")


@pytest.mark.asyncio
async def test_plain_referral_link_never_creates_financial_rewards() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Link partner")
        buyer = await _user(session, "Link buyer")
        session.add(
            ReferralRelation(
                referred_user_id=buyer.id,
                inviter_user_id=partner.id,
                source="link",
            )
        )
        payment = _payment(user_id=buyer.id, amount="100")
        session.add(payment)
        await session.flush()
        payment_tx = await WalletService.credit(
            session,
            user_id=buyer.id,
            amount=Decimal("100"),
            kind="payment",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"plain-link-payment:{payment.id}",
        )

        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
            payment_amount=Decimal("100"),
        )
        await session.commit()

        rewards = list(
            (
                await session.scalars(
                    select(ReferralReward).where(ReferralReward.partner_user_id == partner.id)
                )
            ).all()
        )
        partner_wallet = await session.get(Wallet, partner.id)
        assert rewards == []
        assert partner_wallet is None or Decimal(partner_wallet.balance) == Decimal("0")


@pytest.mark.asyncio
async def test_admin_promo_uses_global_economics_and_requires_partner() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Promo admin")
        partner = await _user(session, "Promo partner")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.read", "promocodes.manage"]},
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        config = await PartnerPromoProgramService.get_config(session)

        created, replayed = await AdminPromoService.create(
            session,
            admin=admin,
            code=f"ADMIN{uuid.uuid4().hex[:8].upper()}",
            partner_user_id=partner.id,
            max_uses=100,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            idempotency_key=f"admin-promo:{uuid.uuid4()}",
            request_id=f"test:{uuid.uuid4()}",
            confirmed=True,
        )
        await session.commit()

        promo = await session.get(PromoCode, uuid.UUID(str(created["id"])))
        assert replayed is False
        assert promo is not None
        assert promo.partner_user_id == partner.id
        assert Decimal(promo.reward_amount) == Decimal(config.welcome_rox)


@pytest.mark.asyncio
async def test_admin_can_change_global_program_economics_without_per_code_rewards() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Program admin")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.read", "promocodes.manage"]},
            is_active=True,
        )
        session.add(admin)
        await session.flush()

        result, replayed = await AdminPromoService.update_program(
            session,
            admin=admin,
            welcome_rox=Decimal("27"),
            first_line_percent=Decimal("31"),
            topup_partner_rox=Decimal("11"),
            is_active=True,
            idempotency_key=f"program-update:{uuid.uuid4()}",
            request_id=f"test:{uuid.uuid4()}",
            confirmed=True,
        )

        assert replayed is False
        assert result["welcome_rox"] == "27"
        assert result["first_line_percent"] == "31"
        assert result["topup_partner_rox"] == "11"
        # Keep the suite isolated: this test proves the mutation but does not persist it.
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires_at",
    [
        datetime.now(UTC) - timedelta(seconds=1),
        datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
    ],
)
async def test_admin_promo_still_rejects_invalid_expiration(expires_at: datetime) -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Expiry admin")
        partner = await _user(session, "Expiry partner")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.manage"]},
            is_active=True,
        )
        session.add(admin)
        await session.flush()

        with pytest.raises(ValueError):
            await AdminPromoService.create(
                session,
                admin=admin,
                code=f"INVALIDEXP{uuid.uuid4().hex[:8].upper()}",
                partner_user_id=partner.id,
                max_uses=100,
                expires_at=expires_at,
                idempotency_key=f"invalid-expiry:{uuid.uuid4()}",
                request_id=f"test:{uuid.uuid4()}",
                confirmed=True,
            )
