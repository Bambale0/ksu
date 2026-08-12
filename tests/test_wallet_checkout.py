from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.payments import list_user_payments
from app.db.models import Payment, User
from app.db.session import SessionFactory

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_user_payment_history_is_owned_and_newest_first() -> None:
    async with SessionFactory() as session:
        owner = User(telegram_id=910000000000001, first_name="WalletOwner")
        other = User(telegram_id=910000000000002, first_name="WalletOther")
        session.add_all([owner, other])
        await session.flush()
        now = datetime.now(timezone.utc)
        older = Payment(
            user_id=owner.id,
            provider="cryptobot",
            amount=Decimal("100.00"),
            currency="RUB",
            rox_amount=Decimal("10.00"),
            status="succeeded",
            payload={"package_id": "small", "request_key": "11111111-1111-4111-8111-111111111111"},
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
        )
        newest = Payment(
            user_id=owner.id,
            provider="tbank",
            amount=Decimal("300.00"),
            currency="RUB",
            rox_amount=Decimal("30.00"),
            status="pending",
            payload={
                "package_id": "medium",
                "request_key": "22222222-2222-4222-8222-222222222222",
                "payment_url": "https://pay.example.invalid/test",
            },
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
        )
        foreign = Payment(
            user_id=other.id,
            provider="yookassa",
            amount=Decimal("500.00"),
            currency="RUB",
            rox_amount=Decimal("50.00"),
            status="pending",
            payload={"package_id": "private"},
            created_at=now,
            updated_at=now,
        )
        session.add_all([older, newest, foreign])
        await session.commit()

        result = await list_user_payments(owner, session, limit=20)
        items = result["items"]
        assert [item["id"] for item in items[:2]] == [str(newest.id), str(older.id)]
        assert all(item["id"] != str(foreign.id) for item in items)
        assert items[0]["package_id"] == "medium"
        assert items[0]["payment_url"] == "https://pay.example.invalid/test"
        assert items[0]["idempotency_key"] == "22222222-2222-4222-8222-222222222222"
        assert items[0]["created_at"]
        assert items[0]["updated_at"]


def test_wallet_checkout_uses_server_packages_and_idempotent_intent() -> None:
    wallet = _read("wallet.js")
    for token in (
        '"/api/v1/payments/packages"',
        '"/api/v1/payments?limit=12"',
        '"Idempotency-Key"',
        "crypto.randomUUID",
        "checkoutIntent",
        "checkoutBusy",
        "package_id: intent.packageId",
        "provider: intent.provider",
    ):
        assert token in wallet, token
    assert "localStorage" not in wallet
    assert "sessionStorage" not in wallet
    assert 'amount: intent' not in wallet
    assert 'credits: intent' not in wallet


def test_wallet_recovers_unknown_payment_without_creating_second_intent() -> None:
    wallet = _read("wallet.js")
    assert "creation_unknown" in wallet
    assert "await refreshPaymentsOnly();" in wallet
    assert "Ответ провайдера неопределён" in wallet
    assert "NONTERMINAL" in wallet
    assert "startPolling(active.id)" in wallet


def test_wallet_uses_telegram_link_apis_with_web_fallback() -> None:
    wallet = _read("wallet.js")
    assert "openTelegramLink" in wallet
    assert "openLink" in wallet
    assert 'window.open(parsed.href, "_blank", "noopener,noreferrer")' in wallet


def test_wallet_ui_has_package_provider_status_and_history_surfaces() -> None:
    html = _read("index.html")
    for element_id in (
        "paymentPackageGrid",
        "paymentProviderGrid",
        "paymentCheckoutButton",
        "paymentCheckoutMessage",
        "paymentStatusSection",
        "paymentStatusCard",
        "paymentHistoryList",
    ):
        assert f'id="{element_id}"' in html
    for provider in ("cryptobot", "tbank", "yookassa"):
        assert f'data-payment-provider="{provider}"' in html
    assert '/mini-app/wallet.js' in html


def test_wallet_styles_and_ci_are_shipped() -> None:
    css = _read("wallet.css")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for token in (
        ".payment-packages",
        ".payment-provider.is-selected",
        ".payment-status-card",
        ".payment-history-row",
    ):
        assert token in css, token
    assert "node --check app/web/mini_app/wallet.js" in workflow
