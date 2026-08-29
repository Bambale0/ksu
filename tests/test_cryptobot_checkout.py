from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionFactory
from app.providers.payments import CreatedPayment, CryptoPayClient
from app.services.crypto_payments import CryptoBotPaymentService


def _telegram_id() -> int:
    return 9_820_000_000_000 + random.randint(1, 999_999_999)


def test_cryptobot_is_configured_only_with_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cryptopay_api_token", "")
    assert CryptoBotPaymentService.provider_configured() is False

    monkeypatch.setattr(settings, "cryptopay_api_token", "crypto-token")
    assert CryptoBotPaymentService.provider_configured() is True


@pytest.mark.asyncio
async def test_cryptobot_checkout_reuses_existing_service_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"RUB":"326.09","USD":"6"}}}',
    )
    monkeypatch.setattr(settings, "cryptopay_api_token", "crypto-token")
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
            external_id="123456",
            payment_url="https://t.me/CryptoBot?start=invoice-test",
            raw={"ok": True, "result": {"invoice_id": 123456}},
        )

    async def fake_aclose(self: CryptoPayClient) -> None:
        return None

    monkeypatch.setattr(CryptoPayClient, "create_payment", fake_create_payment)
    monkeypatch.setattr(CryptoPayClient, "aclose", fake_aclose)
    request_key = str(uuid.uuid4())

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="CryptoBotCheckout")
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
        assert first.amount == Decimal("326.09")
        assert first.currency == "RUB"
        assert first.rox_amount == Decimal("350")
        assert first.payload["base_credits"] == "300"
        assert first.payload["bonus_credits"] == "50"
        assert first.payload["payment_url"].startswith("https://t.me/CryptoBot")
        assert calls == [
            {
                "local_id": str(first.id),
                "amount": "326.09",
                "currency": "RUB",
                "description": "Пополнение ROXY: 300 ROX",
            }
        ]
