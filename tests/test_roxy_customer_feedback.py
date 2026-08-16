import random
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Notification, ReferralRelation, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.notification_events import register_notification_events
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"

register_notification_events()


def _telegram_id() -> int:
    return random.randint(9_880_000_000_000_000, 9_889_999_999_999_999)


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_customer_palette_is_exact_and_loaded_last() -> None:
    feedback = _read("roxy-client-feedback.css")
    brand = _read("roxy-brand.js")
    logo = _read("roxy-logo.svg")

    for token in ("#0B0B10", "#9B5CFF", "#FF5FB7", "#FFFFFF", "#A6A6B3"):
        assert token in feedback
    assert "linear-gradient(110deg, #9B5CFF 0%, #FF5FB7 100%)" in feedback
    assert "#b768ff" not in feedback.lower()
    assert "#8f63ff" not in feedback.lower()
    assert "#ff69c9" not in feedback.lower()
    assert '/mini-app/roxy-client-feedback.css' in brand
    assert brand.index('/mini-app/roxy-client-feedback.css') > brand.index('/mini-app/roxy-approved-surfaces.css')
    assert 'setHeaderColor?.("#0B0B10")' in brand
    assert 'setBackgroundColor?.("#0B0B10")' in brand
    assert 'setBottomBarColor?.("#0B0B10")' in brand
    assert "#9B5CFF" in logo and "#FF5FB7" in logo
    assert "#b768ff" not in logo.lower()


def test_withdrawable_rox_indicator_is_white_silver_not_green() -> None:
    feedback = _read("roxy-client-feedback.css")
    selector = ".roxy-balance-card.withdrawable .roxy-balance-type::before"
    assert selector in feedback
    block = feedback.split(selector, 1)[1].split("}", 1)[0]
    assert "background: #FFFFFF" in block
    assert "border: 1px solid #A6A6B3" in block
    assert "green" not in block.lower()


def test_telegram_back_uses_previous_history_entry_instead_of_forcing_home() -> None:
    runtime = _read("roxy-mobile-runtime.js")
    assert "if (window.history.length > 1)" in runtime
    assert "window.history.back();" in runtime
    assert "history.state?.roxyNavigation" not in runtime
    assert 'window.addEventListener("roxy:route-changed", scheduleBackSync)' in runtime


def test_direct_support_is_configurable_and_has_safe_ticket_fallback() -> None:
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    support = (ROOT / "app" / "bot" / "handlers" / "support.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'support_telegram_url: str = ""' in config
    assert "SUPPORT_TELEGRAM_URL=" in env
    assert 'url.startswith("https://t.me/")' in support
    assert 'text="🆘 Написать в поддержку"' in support
    assert "await _start_ticket(message, state)" in support


@pytest.mark.asyncio
async def test_referral_topups_create_first_and_second_line_telegram_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "referral_second_percent", Decimal("5"))

    async with SessionFactory() as session:
        second_line_partner = User(telegram_id=_telegram_id(), first_name="Second")
        first_line_partner = User(telegram_id=_telegram_id(), first_name="First")
        buyer = User(telegram_id=_telegram_id(), first_name="Anastasiya")
        session.add_all([second_line_partner, first_line_partner, buyer])
        await session.flush()
        session.add_all(
            [
                ReferralRelation(
                    referred_user_id=first_line_partner.id,
                    inviter_user_id=second_line_partner.id,
                ),
                ReferralRelation(
                    referred_user_id=buyer.id,
                    inviter_user_id=first_line_partner.id,
                ),
            ]
        )
        await session.flush()
        payment_tx = await WalletService.credit(
            session,
            user_id=buyer.id,
            amount=Decimal("100"),
            kind="payment",
            reference_type="payment",
            reference_id="feedback-payment",
            idempotency_key=f"feedback-payment:{buyer.id}",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=payment_tx.id,
            payment_amount=Decimal("100"),
        )
        await session.commit()

        first = await session.scalar(
            select(Notification).where(
                Notification.user_id == first_line_partner.id,
                Notification.kind == "referral_line_1_topup",
            )
        )
        second = await session.scalar(
            select(Notification).where(
                Notification.user_id == second_line_partner.id,
                Notification.kind == "referral_line_2_topup",
            )
        )
        assert first is not None
        assert second is not None
        assert first.title == "💰 Пополнение по 1-й линии!"
        assert second.title == "💰 Пополнение по 2-й линии!"
        assert "Пополнение пользователя Anastasiya: 100 ROX." in first.body
        assert "Ваш бонус: +30 ROX (30%)." in first.body
        assert "Ваш бонус: +5 ROX (5%)." in second.body
        assert "Telegram" not in first.body
        assert "Telegram" not in second.body

        deliveries = list(
            (
                await session.scalars(
                    select(NotificationDelivery).where(
                        NotificationDelivery.notification_id.in_([first.id, second.id])
                    )
                )
            ).all()
        )
        assert len(deliveries) == 2
        assert all(item.channel == "telegram" and item.status == "pending" for item in deliveries)