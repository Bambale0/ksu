from __future__ import annotations

import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.db.models import Payment, User, Wallet
from app.db.session import SessionFactory
from app.services.account_profile import AccountProfileService

ROOT = Path(__file__).resolve().parents[1]


def _telegram_id() -> int:
    return 99_000_000_000_000 + random.randint(1, 999_999_999)


def test_text_bot_non_root_handlers_use_shared_back_navigation() -> None:
    keyboards = (ROOT / "app" / "bot" / "keyboards.py").read_text(encoding="utf-8")
    start = (ROOT / "app" / "bot" / "handlers" / "start.py").read_text(encoding="utf-8")
    generation = (ROOT / "app" / "bot" / "handlers" / "generation.py").read_text(
        encoding="utf-8"
    )
    support = (ROOT / "app" / "bot" / "handlers" / "support.py").read_text(encoding="utf-8")
    admin = (ROOT / "app" / "bot" / "handlers" / "admin.py").read_text(encoding="utf-8")

    assert 'BACK_TEXT = "⬅️ Назад"' in keyboards
    assert 'callback_data: str = "nav:main"' in keyboards
    assert "callback_data=callback_data" in keyboards
    assert 'F.data == "nav:main"' in start
    assert "await state.clear()" in start
    assert "back_menu()" in start
    assert "back_menu()" in generation
    assert 'back_menu("support:back_topic")' in support
    assert 'F.data == "support:back_topic"' in support
    assert "back_menu()" in admin


def test_detailed_profile_is_shared_by_bot_and_mini_app() -> None:
    start = (ROOT / "app" / "bot" / "handlers" / "start.py").read_text(encoding="utf-8")
    me = (ROOT / "app" / "api" / "v1" / "me.py").read_text(encoding="utf-8")
    mini = (ROOT / "app" / "web" / "mini_app" / "account-overview.js").read_text(
        encoding="utf-8"
    )
    assert "AccountProfileService.overview" in start
    assert '@router.get("/overview")' in me
    assert 'api("/api/v1/me/overview")' in mini
    assert "Telegram ID" in mini
    assert "Регистрация" in mini
    assert "Платежи" in mini
    assert "localStorage" not in mini
    assert "sessionStorage" not in mini
    assert "innerHTML" not in mini


@pytest.mark.asyncio
async def test_profile_keeps_payment_currency_totals_separate() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Profile")
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("40.00")))
        session.add_all(
            [
                Payment(
                    user_id=user.id,
                    provider="card",
                    external_id=f"usd-{uuid.uuid4()}",
                    amount=Decimal("4.00"),
                    currency="USD",
                    rox_amount=Decimal("30.00"),
                    status="succeeded",
                    payload={},
                ),
                Payment(
                    user_id=user.id,
                    provider="card",
                    external_id=f"rub-{uuid.uuid4()}",
                    amount=Decimal("100.00"),
                    currency="RUB",
                    rox_amount=Decimal("10.00"),
                    status="succeeded",
                    payload={},
                ),
            ]
        )
        await session.commit()
        overview = await AccountProfileService.overview(session, user)

        currencies = overview["payments"]["currencies"]
        assert currencies["USD"]["successful_amount"] == "4.00"
        assert currencies["RUB"]["successful_amount"] == "100.00"
        assert currencies["USD"]["credited"] == "30.00"
        assert currencies["RUB"]["credited"] == "10.00"
        assert "successful_amount" not in overview["payments"]
        text = AccountProfileService.text(overview)
        assert "Telegram ID:" in text
        assert "Регистрация:" in text
        assert "USD: 1 успешных · 4.00 USD" in text
        assert "RUB: 1 успешных · 100.00 RUB" in text
