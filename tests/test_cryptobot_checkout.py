from __future__ import annotations

import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionFactory
from app.providers.payments import CreatedPayment, CryptoPayClient
from app.services.crypto_payments import CryptoBotPaymentService


def _telegram_id() -> int:
    return 9_800_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_cryptobot_checkout_reuses_card_packages_and_applies_topup_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"RUB":"300","USD":"6"}}}',
    )
    monkeypatch.setattr(settings, "cryptopay_api_token", "test:token")
    calls: list[dict[str, str]] = []

    async def fake_create_payment(
        self: CryptoPayClient,
        *,
        local_id: str,
        amount: Decimal,
        currency: str,
        description: str,
    ) -> CreatedPayment:
        calls.append(
            {
                "local_id": local_id,
                "amount": str(amount),
                "currency": currency,
                "description": description,
            }
        )
        return CreatedPayment(
            external_id="4242",
            payment_url="https://t.me/CryptoBot?start=invoice-test",
            raw={"ok": True, "result": {"invoice_id": 4242}},
        )

    async def fake_aclose(self: CryptoPayClient) -> None:
        return None

    monkeypatch.setattr(CryptoPayClient, "create_payment", fake_create_payment)
    monkeypatch.setattr(CryptoPayClient, "aclose", fake_aclose)
    request_key = str(uuid.uuid4())

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="CryptoCheckout")
        session.add(user)
        await session.commit()

        first = await CryptoBotPaymentService.create(
            session,
            user_id=user.id,
            package_id="starter",
            request_key=request_key,
        )
        second = await CryptoBotPaymentService.create(
            session,
            user_id=user.id,
            package_id="starter",
            request_key=request_key,
        )

        assert first.id == second.id
        assert first.provider == "cryptobot"
        assert first.amount == Decimal("300")
        assert first.currency == "RUB"
        assert first.rox_amount == Decimal("350")
        assert first.payload["base_credits"] == "300"
        assert first.payload["bonus_credits"] == "50"
        assert first.payload["payment_url"].startswith("https://t.me/")
        assert calls == [
            {
                "local_id": str(first.id),
                "amount": "300",
                "currency": "RUB",
                "description": "Пополнение ROXY: 300 ROX",
            }
        ]


def test_cryptobot_wallet_is_exposed_as_a_real_payment_method() -> None:
    api_source = Path("app/api/v1/payments.py").read_text(encoding="utf-8")
    wallet_source = Path("frontend/mini-app/components/wallet-parity.tsx").read_text(
        encoding="utf-8"
    )
    payments_source = Path("frontend/mini-app/app/payments/page.tsx").read_text(
        encoding="utf-8"
    )
    telegram_source = Path("frontend/mini-app/lib/telegram.ts").read_text(encoding="utf-8")

    assert '@router.get("/crypto/packages")' in api_source
    assert '@router.post("/crypto/checkout"' in api_source
    assert '@router.post("/crypto/{payment_id}/reconcile")' in api_source
    assert '"/api/v1/payments/crypto/packages"' in wallet_source
    assert '/mini-app/payments/?provider=cryptobot' in wallet_source
    assert "Оплатить через CryptoBot" in wallet_source
    assert '"/api/v1/payments/crypto/checkout"' in payments_source
    assert "CryptoBot" in payments_source
    assert "openPaymentLink" in telegram_source
    assert 'host === "t.me" || host === "telegram.me"' in telegram_source
    assert "openTelegramLink" in telegram_source
