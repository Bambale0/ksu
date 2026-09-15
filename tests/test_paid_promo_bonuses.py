from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.api.v1 import referrals as referrals_api
from app.core.config import settings

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
        welcome_tx = transactions[0]
        assert welcome_tx.reason == "promo_activation_welcome"
        assert welcome_tx.promo_code == promo.code
        assert welcome_tx.partner_id == partner.id
        assert welcome_tx.referral_user_id == user.id
        assert welcome_tx.payment_id is None


@pytest.mark.asyncio
async def test_first_promo_overrides_plain_link_then_partner_is_locked() -> None:
    async with SessionFactory() as session:
        first_partner = await _user(session, "First partner")
        second_partner = await _user(session, "Second partner")
        same_link_user = await _user(session, "Same link user")
        cross_link_user = await _user(session, "Cross link user")
        first_promo = await _promo(session, partner=first_partner)
        second_promo = await _promo(session, partner=second_partner)
        session.add_all(
            [
                ReferralRelation(
                    referred_user_id=same_link_user.id,
                    inviter_user_id=first_partner.id,
                    source="link",
                ),
                ReferralRelation(
                    referred_user_id=cross_link_user.id,
                    inviter_user_id=second_partner.id,
                    source="link",
                ),
            ]
        )
        await session.commit()
        cross_link_user_id = cross_link_user.id
        first_partner_id = first_partner.id
        first_promo_id = first_promo.id
        second_promo_code = second_promo.code

        same_activation = await PromoCodeService.activate(
            session,
            user_id=same_link_user.id,
            code=first_promo.code,
        )
        cross_activation = await PromoCodeService.activate(
            session,
            user_id=cross_link_user.id,
            code=first_promo.code,
        )
        await session.commit()

        assert same_activation.activated is True
        assert cross_activation.activated is True
        same_relation = await session.get(ReferralRelation, same_link_user.id)
        cross_relation = await session.get(ReferralRelation, cross_link_user.id)
        assert same_relation is not None
        assert same_relation.inviter_user_id == first_partner.id
        assert same_relation.source == "promo"
        assert same_relation.promo_id == first_promo.id
        assert cross_relation is not None
        assert cross_relation.inviter_user_id == first_partner.id
        assert cross_relation.source == "promo"
        assert cross_relation.promo_id == first_promo.id

        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.activate(
                session,
                user_id=cross_link_user_id,
                code=second_promo_code,
            )
        await session.rollback()
        assert exc_info.value.code == "already_attributed"
        locked = await session.get(ReferralRelation, cross_link_user_id)
        assert locked is not None
        assert locked.inviter_user_id == first_partner_id
        assert locked.source == "promo"
        assert locked.promo_id == first_promo_id


@pytest.mark.asyncio
async def test_partner_promo_activation_respects_referral_hourly_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 1)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 0)
    monkeypatch.setattr(settings, "referral_antifraud_burst_max", 0)
    monkeypatch.setattr(settings, "referral_antifraud_burst_window_seconds", 0)

    async with SessionFactory() as session:
        partner = await _user(session, "Limited partner")
        existing_referral = await _user(session, "Existing referral")
        promo_user = await _user(session, "Blocked promo user")
        promo = await _promo(session, partner=partner)
        promo_user_id = promo_user.id
        promo_id = promo.id
        session.add(
            ReferralRelation(
                referred_user_id=existing_referral.id,
                inviter_user_id=partner.id,
                source="link",
            )
        )
        await session.commit()

        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.activate(
                session,
                user_id=promo_user_id,
                code=promo.code,
            )
        await session.rollback()

        assert exc_info.value.code == "referral_hourly_limit"
        assert exc_info.value.preserve_transaction is True
        assert await session.get(ReferralRelation, promo_user_id) is None
        assert await session.get(Wallet, promo_user_id) is None
        stored = await session.get(PromoCode, promo_id)
        assert stored is not None
        assert stored.uses_count == 0


@pytest.mark.asyncio
async def test_legacy_pending_payment_promo_is_honored_after_program_upgrade() -> None:
    async with SessionFactory() as session:
        user = await _user(session, "Legacy pending user")
        promo = PromoCode(
            code=f"LEGACY{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("7"),
            partner_user_id=None,
            max_uses=100,
            uses_count=0,
            is_active=True,
        )
        payment = Payment(
            user_id=user.id,
            provider="yookassa",
            amount=Decimal("100"),
            currency="RUB",
            rox_amount=Decimal("100"),
            status="pending",
            payload={
                "package_id": "legacy-p100",
                "base_credits": "100",
                "promo_id": "",
                "promo_code": promo.code,
                "promo_reward_credits": "7",
                "promo_bonus_status": "reserved",
                "bonus_credits": "7",
                "credited_credits": "107",
            },
        )
        session.add_all([promo, payment])
        await session.flush()
        payment.payload = {**payment.payload, "promo_id": str(promo.id)}
        redemption = PromoRedemption(
            promo_id=promo.id,
            user_id=user.id,
            payment_id=payment.id,
            status="pending",
            reserved_until=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(redemption)
        await session.commit()

        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded", "legacy": True},
        )

        wallet = await session.get(Wallet, user.id)
        await session.refresh(promo)
        await session.refresh(redemption)
        await session.refresh(payment)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("107.00")
        assert promo.uses_count == 1
        assert redemption.status == "applied"
        assert redemption.redeemed_at is not None
        assert payment.payload["promo_bonus_status"] == "applied"
        assert payment.payload["credited_credits"] == "107"



@pytest.mark.asyncio
async def test_activation_preserves_live_legacy_reservation_until_payment_settles() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Legacy reservation partner")
        user = await _user(session, "Legacy reservation user")
        config = await PartnerPromoProgramService.get_config(session)
        promo = PromoCode(
            code=f"LEGACYACT{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("7"),
            partner_user_id=partner.id,
            max_uses=1,
            uses_count=0,
            is_active=True,
        )
        payment = Payment(
            user_id=user.id,
            provider="yookassa",
            amount=Decimal("100"),
            currency="RUB",
            rox_amount=Decimal("100"),
            status="pending",
            payload={
                "package_id": "legacy-activation-p100",
                "base_credits": "100",
                "promo_id": "",
                "promo_code": promo.code,
                "promo_reward_credits": "7",
                "promo_bonus_status": "reserved",
                "bonus_credits": "7",
                "credited_credits": "107",
            },
        )
        session.add_all([promo, payment])
        await session.flush()
        payment.payload = {**payment.payload, "promo_id": str(promo.id)}
        redemption = PromoRedemption(
            promo_id=promo.id,
            user_id=user.id,
            payment_id=payment.id,
            status="pending",
            reserved_until=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(redemption)
        await session.commit()

        activation = await PromoCodeService.activate(
            session,
            user_id=user.id,
            code=promo.code,
        )
        await session.commit()

        relation = await session.get(ReferralRelation, user.id)
        wallet = await session.get(Wallet, user.id)
        await session.refresh(promo)
        await session.refresh(redemption)
        assert activation.activated is True
        assert relation is not None
        assert relation.source == "promo"
        assert relation.inviter_user_id == partner.id
        assert relation.promo_id == promo.id
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal(config.welcome_rox)
        assert promo.uses_count == 0
        assert redemption.status == "pending"
        assert redemption.payment_id == payment.id
        assert redemption.reserved_until is not None

        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded", "legacy": True},
        )

        wallet = await session.get(Wallet, user.id)
        await session.refresh(promo)
        await session.refresh(redemption)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal(config.welcome_rox) + Decimal("107.00")
        assert promo.uses_count == 1
        assert redemption.status == "applied"
        assert redemption.redeemed_at is not None


@pytest.mark.asyncio
async def test_live_legacy_reservation_holds_capacity_but_owner_can_activate() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Capacity partner")
        holder = await _user(session, "Capacity holder")
        newcomer = await _user(session, "Capacity newcomer")
        promo = PromoCode(
            code=f"LEGACYCAP{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("7"),
            partner_user_id=partner.id,
            max_uses=1,
            uses_count=0,
            is_active=True,
        )
        payment = Payment(
            user_id=holder.id,
            provider="yookassa",
            amount=Decimal("100"),
            currency="RUB",
            rox_amount=Decimal("100"),
            status="pending",
            payload={"base_credits": "100"},
        )
        session.add_all([promo, payment])
        await session.flush()
        session.add(
            PromoRedemption(
                promo_id=promo.id,
                user_id=holder.id,
                payment_id=payment.id,
                status="pending",
                reserved_until=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.commit()
        promo_id = promo.id
        promo_code = promo.code
        holder_id = holder.id
        newcomer_id = newcomer.id

    async with SessionFactory() as session:
        with pytest.raises(PromoCodeError) as exc_info:
            await PromoCodeService.activate(
                session,
                user_id=newcomer_id,
                code=promo_code,
            )
        await session.rollback()
        assert exc_info.value.code == "usage_limit_reached"

    async with SessionFactory() as session:
        activation = await PromoCodeService.activate(
            session,
            user_id=holder_id,
            code=promo_code,
        )
        await session.commit()
        promo = await session.get(PromoCode, promo_id)
        redemption = await session.scalar(
            select(PromoRedemption).where(
                PromoRedemption.promo_id == promo_id,
                PromoRedemption.user_id == holder_id,
            )
        )
        assert activation.activated is True
        assert promo is not None and promo.uses_count == 0
        assert redemption is not None and redemption.status == "pending"
        assert await PromoCodeService.remaining_uses(session, promo=promo) == 0


def test_partner_promo_migration_does_not_destroy_pending_legacy_reservations() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0038_partner_promo_program.py"
    ).read_text(encoding="utf-8")
    assert "SET status = 'released'" not in migration


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
        reward = rewards[0]
        assert reward.reason == "partner_referral_commission"
        assert reward.promo_id == promo.id
        assert reward.promo_code == promo.code
        assert reward.payment_id == payment.id
        assert reward.partner_user_id == partner.id
        assert reward.source_user_id == buyer.id

        payment_tx = await session.scalar(
            select(WalletTransaction).where(
                WalletTransaction.user_id == buyer.id,
                WalletTransaction.kind == "payment",
                WalletTransaction.reference_id == str(payment.id),
            )
        )
        assert payment_tx is not None
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
            payment_amount=Decimal("999999"),
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
        )
        await session.flush()

        bonus_transactions = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.user_id == partner.id,
                        WalletTransaction.kind == "partner_promo_topup_bonus",
                    )
                )
            ).all()
        )
        assert len(bonus_transactions) == 1
        bonus_tx = bonus_transactions[0]
        assert bonus_tx.reason == "partner_referral_topup_bonus"
        assert bonus_tx.promo_code == promo.code
        assert bonus_tx.partner_id == partner.id
        assert bonus_tx.referral_user_id == buyer.id
        assert bonus_tx.payment_id == payment.id
        assert len(
            list(
                (
                    await session.scalars(
                        select(ReferralReward).where(
                            ReferralReward.source_transaction_id == payment_tx.id
                        )
                    )
                ).all()
            )
        ) == 1
        await session.refresh(partner_wallet)
        assert Decimal(partner_wallet.balance) == Decimal(config.topup_partner_rox)
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
async def test_partner_lists_only_their_assigned_promo_codes() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Partner promo owner")
        other_partner = await _user(session, "Other promo owner")
        owned = await _promo(session, partner=partner, max_uses=100)
        owned.uses_count = 4
        disabled = await _promo(session, partner=partner, max_uses=None)
        disabled.is_active = False
        foreign = await _promo(session, partner=other_partner, max_uses=50)
        await session.commit()

        result = await referrals_api.promocodes(partner, session, limit=100, offset=0)
        items = {item["code"]: item for item in result["items"]}

        assert set(items) == {owned.code, disabled.code}
        assert foreign.code not in items
        assert items[owned.code]["uses_count"] == 4
        assert items[owned.code]["remaining_uses"] == 96
        assert items[owned.code]["is_active"] is True
        assert items[disabled.code]["remaining_uses"] is None
        assert items[disabled.code]["is_active"] is False


@pytest.mark.asyncio
async def test_admin_cannot_reactivate_legacy_ownerless_promo() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Legacy promo admin")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.manage"]},
            is_active=True,
        )
        promo = PromoCode(
            code=f"OWNERLESS{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("25"),
            partner_user_id=None,
            max_uses=100,
            uses_count=0,
            is_active=False,
        )
        session.add_all([admin, promo])
        await session.flush()

        with pytest.raises(ValueError, match="partner"):
            await AdminPromoService.set_active(
                session,
                admin=admin,
                promo_id=promo.id,
                is_active=True,
                idempotency_key=f"ownerless-reactivate:{uuid.uuid4()}",
                request_id=f"test:{uuid.uuid4()}",
                confirmed=True,
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_admin_campaign_update_cannot_reactivate_legacy_ownerless_promo() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Legacy campaign promo admin")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.manage"]},
            is_active=True,
        )
        promo = PromoCode(
            code=f"CAMPAIGNOWNERLESS{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("25"),
            partner_user_id=None,
            max_uses=100,
            uses_count=0,
            is_active=False,
        )
        session.add_all([admin, promo])
        await session.flush()

        with pytest.raises(ValueError, match="partner"):
            await AdminPromoService.update_campaign(
                session,
                admin=admin,
                promo_id=promo.id,
                max_uses=None,
                expires_at=None,
                is_active=True,
                idempotency_key=f"ownerless-campaign-reactivate:{uuid.uuid4()}",
                request_id=f"test:{uuid.uuid4()}",
                confirmed=True,
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_admin_promo_create_rejects_missing_partner_instead_of_creating_dead_code() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Ownerless promo admin")
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={"allow": ["promocodes.manage"]},
            is_active=True,
        )
        session.add(admin)
        await session.flush()

        with pytest.raises(ValueError, match="partner_user_id is required"):
            await AdminPromoService.create(
                session,
                admin=admin,
                code=f"OWNERLESS{uuid.uuid4().hex[:8].upper()}",
                partner_user_id=None,
                max_uses=100,
                expires_at=datetime.now(UTC) + timedelta(days=30),
                idempotency_key=f"ownerless-promo:{uuid.uuid4()}",
                request_id=f"test:{uuid.uuid4()}",
                confirmed=True,
            )
        await session.rollback()


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
        assert Decimal(str(result["welcome_rox"])) == Decimal("27")
        assert Decimal(str(result["first_line_percent"])) == Decimal("31")
        assert Decimal(str(result["topup_partner_rox"])) == Decimal("11")
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


@pytest.mark.asyncio
async def test_active_partner_promo_state_persists_and_marks_future_payment() -> None:
    async with SessionFactory() as session:
        partner = await _user(session, "Persistent promo partner")
        user = await _user(session, "Persistent promo user")
        promo = await _promo(session, partner=partner)
        await session.commit()

        activation = await PromoCodeService.activate(
            session,
            user_id=user.id,
            code=promo.code,
        )
        await session.commit()
        assert activation.activated is True

        state = await PromoCodeService.active_state(session, user_id=user.id)
        assert state["active"] is True
        assert state["code"] == promo.code
        assert state["partner_user_id"] == str(partner.id)
        assert Decimal(str(state["welcome_rox_granted"])) == Decimal("25.00")
        assert Decimal(str(state["package_discount_percent"])) == Decimal("0")

        payment = Payment(
            user_id=user.id,
            provider="yookassa",
            amount=Decimal("300"),
            currency="RUB",
            rox_amount=Decimal("300"),
            status="pending",
            payload={
                "package_id": "persistent-p300",
                "base_credits": "300",
                "bonus_credits": "0",
                "credited_credits": "300",
            },
        )
        session.add(payment)
        await session.flush()

        attached = await PromoCodeService.reserve_for_payment(
            session,
            payment=payment,
            code=None,
        )
        await session.flush()

        assert attached is not None
        assert attached.id == promo.id
        assert payment.payload["promo_code"] == promo.code
        assert payment.payload["promo_partner_user_id"] == str(partner.id)
        assert payment.payload["promo_metadata_source"] == "attribution"
        assert payment.payload["promo_bonus_status"] == "activated"
        assert payment.payload["bonus_credits"] == "0"
        assert payment.payload["credited_credits"] == "300"
