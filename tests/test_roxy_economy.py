import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy import select

from app.api.v1.referrals import stats
from app.core.config import settings
from app.db.models import Payment, ReferralRelation, ReferralReward, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.partner_wallet import PartnerWalletTransferService
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


@pytest.mark.asyncio
async def test_registration_and_invite_create_rox_wallet_bonuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", Decimal("50"))
    monkeypatch.setattr(settings, "invite_bonus_rox", Decimal("30"))
    async with SessionFactory() as session:
        inviter = User(telegram_id=_telegram_id(), first_name="Inviter")
        friend_telegram_id = _telegram_id()
        session.add(inviter)
        await session.flush()
        await UserService.get_or_create(
            session,
            TelegramUser(id=friend_telegram_id, is_bot=False, first_name="Friend"),
            inviter_telegram_id=inviter.telegram_id,
        )
        await session.commit()

        friend = await UserService.get_by_telegram_id(session, friend_telegram_id)
        assert friend is not None
        friend_wallet = await session.get(Wallet, friend.id)
        inviter_wallet = await session.get(Wallet, inviter.id)
        assert friend_wallet is not None and friend_wallet.balance == Decimal("50")
        assert inviter_wallet is not None and inviter_wallet.balance == Decimal("30")

        kinds = set(
            (
                await session.scalars(
                    select(WalletTransaction.kind).where(
                        WalletTransaction.user_id.in_([friend.id, inviter.id])
                    )
                )
            ).all()
        )
        assert {"welcome_bonus", "referral_invite_bonus"}.issubset(kinds)


@pytest.mark.asyncio
async def test_referral_percent_uses_actual_paid_rub_not_credited_rox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    async with SessionFactory() as session:
        inviter = User(telegram_id=_telegram_id(), first_name="Partner")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([inviter, buyer])
        await session.flush()
        session.add(ReferralRelation(referred_user_id=buyer.id, inviter_user_id=inviter.id))
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
async def test_partner_earnings_can_move_to_rox_once_and_reduce_cash_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    async with SessionFactory() as session:
        partner = User(telegram_id=_telegram_id(), first_name="Partner")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([partner, buyer])
        await session.flush()
        session.add(ReferralRelation(referred_user_id=buyer.id, inviter_user_id=partner.id))
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
        assert wallet.balance == Decimal("40.00")
        accounting = await PartnerWalletTransferService.accounting(session, partner.id)
        assert accounting["total_earned"] == Decimal("90.00")
        assert accounting["transferred_to_rox"] == Decimal("40.00")
        assert accounting["available"] == Decimal("50.00")


@pytest.mark.asyncio
async def test_stats_expose_simple_wallet_and_partner_rub_contract() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Economy")
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("280")))
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
        assert payload["welcome_bonus_rox"] == "50"
        assert payload["invite_bonus_rox"] == "30"
        assert payload["prompt_repeat_bonus_rox"] == "5"
        assert payload["first_line_percent"] == "30"
        assert payload["second_line_percent"] == "5"
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
    assert '"/api/v1/payments/card/packages"' in api
    assert '"/api/v1/payments/card/checkout"' in api

    # Partner cash accounting is a separate backend domain and must never be
    # presented as spendable ROX in the customer wallet.
    assert "partner_balance_rub" not in app
    assert "transferred_to_rox" not in app
    assert "Бонусные ROX" not in app
    assert "Выводимые ROX" not in app
