import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy import select

from app.api.v1.referrals import stats
from app.core.config import settings
from app.db.models import Payment, PromoCode, ReferralRelation, ReferralReward, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.partner_promo_program import PartnerPromoProgramService
from app.services.partner_wallet import PartnerWalletTransferService
from app.services.payments import PaymentService
from app.services.referrals import ReferralService
from app.services.users import UserService
from app.services.wallet import WalletService

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _telegram_id() -> int:
    return random.randint(9_700_000_000_000_000, 9_799_999_999_999_999)


async def _paid_transaction(
    session,
    *,
    buyer: User,
    paid_rub: Decimal,
    credited_rox: Decimal,
    key: str,
) -> WalletTransaction:
    payment = Payment(
        user_id=buyer.id,
        provider="economy-test",
        external_id=f"economy-test-{uuid.uuid4()}",
        amount=paid_rub,
        currency="RUB",
        rox_amount=credited_rox,
        status="succeeded",
        payload={},
    )
    session.add(payment)
    await session.flush()
    return await WalletService.credit(
        session,
        user_id=buyer.id,
        amount=credited_rox,
        kind="payment",
        reference_type="payment",
        reference_id=str(payment.id),
        idempotency_key=key,
    )


async def _promo_attribution(session, *, partner: User, buyer: User) -> PromoCode:
    config = await PartnerPromoProgramService.get_config(session)
    promo = PromoCode(
        code=f"ECON{uuid.uuid4().hex[:12].upper()}",
        reward_amount=Decimal(config.welcome_rox),
        partner_user_id=partner.id,
        max_uses=100,
        uses_count=1,
        is_active=True,
    )
    session.add(promo)
    await session.flush()
    session.add(
        ReferralRelation(
            referred_user_id=buyer.id,
            inviter_user_id=partner.id,
            source="promo",
            promo_id=promo.id,
        )
    )
    await session.flush()
    return promo


@pytest.mark.asyncio
async def test_registration_grants_db_welcome_once_and_legacy_env_cannot_override_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Registration economics are DB-owned. Legacy env knobs remain compatibility-only.
    monkeypatch.setattr(settings, "start_balance_rox", Decimal("50"))
    monkeypatch.setattr(settings, "invite_bonus_rox", Decimal("30"))
    async with SessionFactory() as session:
        config = await PartnerPromoProgramService.get_config(session)
        assert Decimal(config.welcome_rox) == Decimal("25")

        inviter = User(telegram_id=_telegram_id(), first_name="Inviter")
        friend_telegram_id = _telegram_id()
        session.add(inviter)
        await session.flush()

        telegram_user = TelegramUser(id=friend_telegram_id, is_bot=False, first_name="Friend")
        first = await UserService.get_or_create(
            session,
            telegram_user,
            inviter_telegram_id=inviter.telegram_id,
        )
        await session.commit()

        # Re-opening the bot must not duplicate the registration bonus.
        second = await UserService.get_or_create(
            session,
            telegram_user,
            inviter_telegram_id=inviter.telegram_id,
        )
        await session.commit()

        friend = await UserService.get_by_telegram_id(session, friend_telegram_id)
        assert friend is not None
        assert first.id == second.id == friend.id
        friend_wallet = await session.get(Wallet, friend.id)
        inviter_wallet = await session.get(Wallet, inviter.id)
        relation = await session.get(ReferralRelation, friend.id)

        assert friend_wallet is not None and friend_wallet.balance == Decimal("25")
        assert inviter_wallet is None or inviter_wallet.balance == Decimal("0")
        assert relation is not None
        assert relation.inviter_user_id == inviter.id
        assert relation.source == "link"
        assert relation.promo_id is None

        transactions = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(WalletTransaction.user_id == friend.id)
                )
            ).all()
        )
        registration = [tx for tx in transactions if tx.kind == "welcome_bonus"]
        assert len(registration) == 1
        assert registration[0].amount == Decimal("25")
        assert registration[0].reason == "registration_welcome"
        assert "referral_invite_bonus" not in {tx.kind for tx in transactions}


@pytest.mark.asyncio
async def test_package_bonus_is_zero_without_promo_and_applied_once_after_promo_payment() -> None:
    async with SessionFactory() as session:
        plain = User(telegram_id=_telegram_id(), first_name="Plain buyer")
        partner = User(telegram_id=_telegram_id(), first_name="Partner")
        promo_buyer = User(telegram_id=_telegram_id(), first_name="Promo buyer")
        session.add_all([plain, partner, promo_buyer])
        await session.flush()

        plain_payment = Payment(
            user_id=plain.id,
            provider="yookassa",
            amount=Decimal("500"),
            currency="RUB",
            rox_amount=Decimal("500"),
            status="pending",
            payload={
                "package_id": "p500",
                "base_credits": "500",
                "package_bonus_credits": "0",
                "promo_package_bonus_credits": "50",
                "promo_bonus_credits": "0",
                "bonus_credits": "0",
                "credited_credits": "500",
            },
        )
        session.add(plain_payment)
        await session.commit()

        await PaymentService.complete(
            session,
            payment_id=plain_payment.id,
            provider_payload={"status": "succeeded"},
        )
        plain_wallet = await session.get(Wallet, plain.id)
        assert plain_wallet is not None
        assert Decimal(plain_wallet.balance) == Decimal("500")
        await session.refresh(plain_payment)
        assert plain_payment.payload["promo_bonus_credits"] == "0"
        assert plain_payment.payload["credited_credits"] == "500"

        promo = await _promo_attribution(session, partner=partner, buyer=promo_buyer)
        promo_payment = Payment(
            user_id=promo_buyer.id,
            provider="yookassa",
            amount=Decimal("1000"),
            currency="RUB",
            rox_amount=Decimal("1000"),
            status="pending",
            payload={
                "package_id": "p1000",
                "base_credits": "1000",
                "package_bonus_credits": "0",
                "promo_package_bonus_credits": "150",
                "promo_bonus_credits": "0",
                "bonus_credits": "0",
                "credited_credits": "1000",
                "promo_id": str(promo.id),
                "promo_code": promo.code,
                "promo_partner_user_id": str(partner.id),
                "promo_metadata_source": "attribution",
                "promo_bonus_status": "activated",
            },
        )
        session.add(promo_payment)
        await session.commit()

        # Merely having an active promo still grants nothing before settlement.
        before = await session.get(Wallet, promo_buyer.id)
        assert before is None or Decimal(before.balance) == Decimal("0")

        completed = await PaymentService.complete(
            session,
            payment_id=promo_payment.id,
            provider_payload={"status": "succeeded"},
        )
        promo_wallet = await session.get(Wallet, promo_buyer.id)
        assert promo_wallet is not None
        assert Decimal(promo_wallet.balance) == Decimal("1150")
        assert Decimal(completed.rox_amount) == Decimal("1000")
        assert completed.payload["package_bonus_credits"] == "0"
        assert completed.payload["promo_bonus_credits"] == "150"
        assert completed.payload["promo_reward_credits"] == "150"
        assert completed.payload["bonus_credits"] == "150"
        assert completed.payload["credited_credits"] == "1150"

        # Settlement replay is idempotent.
        await PaymentService.complete(
            session,
            payment_id=promo_payment.id,
            provider_payload={"status": "succeeded", "replay": True},
        )
        await session.refresh(promo_wallet)
        assert Decimal(promo_wallet.balance) == Decimal("1150")


@pytest.mark.asyncio
async def test_referral_percent_uses_actual_paid_rub_not_credited_rox() -> None:
    async with SessionFactory() as session:
        inviter = User(telegram_id=_telegram_id(), first_name="Partner")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([inviter, buyer])
        await session.flush()
        await _promo_attribution(session, partner=inviter, buyer=buyer)
        payment_tx = await _paid_transaction(
            session,
            buyer=buyer,
            paid_rub=Decimal("326.10"),
            credited_rox=Decimal("350"),
            key=f"test-payment:{buyer.id}",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
            # Deliberately wrong caller value: service must ignore it and read Payment.amount.
            payment_amount=Decimal("350"),
        )
        await session.commit()

        reward = await session.scalar(
            select(ReferralReward).where(
                ReferralReward.partner_user_id == inviter.id,
                ReferralReward.source_transaction_id == payment_tx.id,
                ReferralReward.level == 1,
            )
        )
        assert reward is not None
        assert reward.amount == Decimal("97.83")


@pytest.mark.asyncio
async def test_partner_earnings_can_move_to_rox_once_and_reduce_cash_available() -> None:
    async with SessionFactory() as session:
        partner = User(telegram_id=_telegram_id(), first_name="Partner")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([partner, buyer])
        await session.flush()
        await _promo_attribution(session, partner=partner, buyer=buyer)
        payment_tx = await _paid_transaction(
            session,
            buyer=buyer,
            paid_rub=Decimal("300"),
            credited_rox=Decimal("300"),
            key=f"partner-transfer-payment:{buyer.id}",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
            payment_amount=Decimal("300"),
        )
        await session.flush()

        first = await PartnerWalletTransferService.transfer(
            session,
            user_id=partner.id,
            amount=Decimal("40"),
            idempotency_key="partner-transfer-test-key",
        )
        second = await PartnerWalletTransferService.transfer(
            session,
            user_id=partner.id,
            amount=Decimal("40"),
            idempotency_key="partner-transfer-test-key",
        )
        await session.commit()

        assert first.id == second.id
        wallet = await session.get(Wallet, partner.id)
        assert wallet is not None
        # 40 ROX converted from cash earnings + 10 ROX fixed promo top-up bonus.
        assert wallet.balance == Decimal("50.00")
        accounting = await PartnerWalletTransferService.accounting(session, partner.id)
        assert accounting["total_earned"] == Decimal("90.00")
        assert accounting["transferred_to_rox"] == Decimal("40.00")
        assert accounting["available"] == Decimal("50.00")


@pytest.mark.asyncio
async def test_stats_expose_simple_wallet_and_partner_rub_contract(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Economy")
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("280")))
        promo = PromoCode(
            code=f"ECON{uuid.uuid4().hex[:8].upper()}",
            reward_amount=Decimal("25"),
            partner_user_id=user.id,
            max_uses=100,
            uses_count=7,
            is_active=True,
        )
        session.add(promo)
        await session.commit()

        payload = await stats(user, session)
        assert payload["rox_balance"] == "280.00"
        assert payload["partner_balance_rub"] == "0"
        assert payload["withdrawable_rub"] == "0"
        assert payload["pending_referral_rub"] == "0"
        assert payload["partner_total_earned_rub"] == "0"
        assert payload["transferred_to_rox"] == "0"
        assert payload["bonus_rox"] == "280.00"  # wallet compatibility only
        assert payload["rub_per_rox"] == "1"
        assert payload["welcome_bonus_rox"] == "25.00"
        assert payload["registration_bonus_rox"] == "25.00"
        assert payload["invite_bonus_rox"] == "0"
        assert payload["prompt_repeat_bonus_rox"] == "5"
        assert payload["first_line_percent"] == "30.00"
        assert payload["promo_welcome_rox"] == "25.00"
        assert payload["promo_topup_partner_rox"] == "10.00"
        assert payload["promo_program_active"] is True
        assert payload["promo_codes"] == [
            {
                "id": str(promo.id),
                "code": promo.code,
                "is_active": True,
                "uses_count": 7,
                "max_uses": 100,
                "expires_at": None,
            }
        ]
        assert payload["second_line_percent"] == "0"
        assert payload["minimum_withdrawal"] == "3000"
        assert payload["minimum_withdrawal_rub"] == "3000"
        assert payload["withdrawal_status"] == "NONE"
        for misleading_key in (
            "withdrawable_rox",
            "withdrawable_pending_rox",
            "partner_total_earned_rox",
            "minimum_withdrawal_rox",
        ):
            assert misleading_key not in payload


def test_prompt_repeat_bonus_is_idempotent_success_only_and_blocks_self_reward() -> None:
    provider = (ROOT / "app" / "services" / "generation_provider.py").read_text(encoding="utf-8")
    generation_create = (ROOT / "app" / "services" / "generations.py").read_text(encoding="utf-8")
    assert 'generation.action_type != "remix"' in provider
    assert "source.user_id == generation.user_id" in provider
    assert 'kind="prompt_repeat_bonus"' in provider
    assert 'idempotency_key=f"prompt-repeat:{generation.id}"' in provider
    assert "settings.prompt_repeat_bonus_rox" in provider
    assert "await cls._award_prompt_repeat_bonus(session, generation)" in provider
    assert provider.index("if task.state == \"success\":") < provider.index(
        "await cls._award_prompt_repeat_bonus(session, generation)"
    )
    assert 'kind="prompt_repeat_bonus"' not in generation_create


def test_public_roxy_menu_is_mini_app_only() -> None:
    keyboard = (ROOT / "app" / "bot" / "keyboards.py").read_text(encoding="utf-8")
    launcher = keyboard.split("def app_launcher_menu(", 1)[1].split("\ndef _route_button", 1)[0]
    main_menu = keyboard.split("def main_menu()", 1)[1]
    assert 'text="🚀 Открыть ROXY"' in launcher
    assert 'return app_launcher_menu(route="catalog")' in main_menu
    for label in (
        "✨ Создать",
        "▦ Каталог",
        "≡ История",
        "👤 Профиль",
        "💳 Пополнить ROX",
        "👥 Пригласить в ROXY",
    ):
        assert label not in main_menu
    assert 'route="wallet"' not in main_menu
    assert 'callback_data="referrals"' not in main_menu


def test_react_wallet_keeps_rox_separate_from_partner_rubles() -> None:
    app = (FRONTEND / "components" / "roxy-app.tsx").read_text(encoding="utf-8")
    api = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "lib" / "types.ts").read_text(encoding="utf-8")

    assert "balance_rox" in types
    assert '`${compact(me.balance_rox)} ROX`' in app
    assert 'api.paymentPackages()' in app
    assert 'api.transactions()' in app
    assert '"/api/v1/me/transactions"' in api
    assert '"/api/v1/payments/yookassa/packages"' in api
    assert 'body: JSON.stringify({ provider: "yookassa", package_id: packageId })' in api
    assert '"/api/v1/payments/card/packages"' not in api
    assert '"/api/v1/payments/card/checkout"' not in api

    # Partner cash accounting is a separate backend domain and must never be
    # presented as spendable ROX in the customer wallet.
    assert "partner_balance_rub" not in app
    assert "transferred_to_rox" not in app
    assert "Бонусные ROX" not in app
    assert "Выводимые ROX" not in app
