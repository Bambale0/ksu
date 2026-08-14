from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy import select

from app.api.v1.referrals import stats
from app.core.config import settings
from app.db.models import User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.users import UserService

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


@pytest.mark.asyncio
async def test_registration_and_invite_create_spend_only_rox_bonuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", Decimal("50"))
    monkeypatch.setattr(settings, "invite_bonus_rox", Decimal("30"))
    async with SessionFactory() as session:
        inviter = User(telegram_id=930000000000001, first_name="Inviter")
        session.add(inviter)
        await session.flush()
        await UserService.get_or_create(
            session,
            TelegramUser(
                id=930000000000002,
                is_bot=False,
                first_name="Friend",
            ),
            inviter_telegram_id=inviter.telegram_id,
        )
        await session.commit()

        friend = await UserService.get_by_telegram_id(session, 930000000000002)
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
async def test_stats_expose_reference_economy_contract() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=930000000000003, first_name="Economy")
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("280")))
        await session.commit()

        payload = await stats(user, session)
        assert payload["bonus_rox"] == "280.00"
        assert payload["withdrawable_rox"] == "0.00"
        assert payload["rub_per_rox"] == "1"
        assert payload["welcome_bonus_rox"] == "50"
        assert payload["invite_bonus_rox"] == "30"
        assert payload["prompt_repeat_bonus_rox"] == "5"
        assert payload["first_line_percent"] == "30"
        assert payload["second_line_percent"] == "5"
        assert payload["minimum_withdrawal_rox"] == "3000.00"
        assert payload["withdrawal_status"] == "NONE"


def test_prompt_repeat_bonus_is_idempotent_and_blocks_self_reward() -> None:
    source = (ROOT / "app" / "services" / "generations.py").read_text(encoding="utf-8")
    assert 'action_type == "remix"' in source
    assert "source.user_id != user_id" in source
    assert 'kind="prompt_repeat_bonus"' in source
    assert 'idempotency_key=f"prompt-repeat:{generation.id}"' in source
    assert "settings.prompt_repeat_bonus_rox" in source


def test_public_roxy_menu_matches_reference() -> None:
    keyboard = (ROOT / "app" / "bot" / "keyboards.py").read_text(encoding="utf-8")
    for label in (
        "✨ Создать",
        "🔁 Промпты",
        "💎 Мои ROX",
        "👥 Заработать",
        "👤 Профиль",
    ):
        assert label in keyboard
    main_menu = keyboard.split("def main_menu()", 1)[1]
    for legacy in ("Пакетная обработка", "AI-инструменты", "Тренды", "🌐 Лента", "🆘 Поддержка"):
        assert legacy not in main_menu


def test_mini_app_economy_matches_reference_copy_and_split_balances() -> None:
    script = (MINI / "roxy-economy.js").read_text(encoding="utf-8")
    style = (MINI / "roxy-economy.css").read_text(encoding="utf-8")
    integration = (MINI / "shell-integration.js").read_text(encoding="utf-8")
    for token in (
        "1 ROX = 1 ₽",
        "🟣 Бонусные ROX",
        "🟢 Выводимые ROX",
        "Приветственный бонус",
        "Приглашённый друг",
        "Повтор промпта",
        "Минимальный вывод",
        "Создать",
        "Промпты",
        "Мои ROX",
        "Заработать",
        "Профиль",
        '"/api/v1/referrals/stats"',
    ):
        assert token in script
    assert "roxy-balance-grid" in style
    assert "roxy-rule-row" in style
    assert "#studioHomeOrchestration" in style
    assert '/mini-app/roxy-economy.js' in integration
    assert '/mini-app/roxy-economy.css' in integration
