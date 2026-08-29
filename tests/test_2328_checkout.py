from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.payment_2328_config import payment_2328_settings
from app.db.models import User
from app.db.session import SessionFactory
from app.providers.payment_2328 import (
    Payment2328Client,
    make_2328_signature,
    verify_2328_webhook,
)
from app.providers.payments import CreatedPayment
from app.services.payment_2328 import Payment2328Service


def _telegram_id() -> int:
    return 9_810_000_000_000 + random.randint(1, 999_999_999)


def test_2328_signature_matches_documented_hmac_algorithm() -> None:
    payload = {
        "amount": "326.09",
        "currency": "RUB",
        "order_id": "ORDER-123",
        "description": "Пополнение ROXY",
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(
        b"secret",
        base64.b64encode(body.encode("utf-8")),
        hashlib.sha256,
    ).hexdigest()

    assert make_2328_signature(payload, "secret") == expected


def test_2328_webhook_signature_is_verified_before_state_changes() -> None:
    payload = {
        "uuid": "provider-uuid",
        "order_id": "ORDER-123",
        "amount": "326.09000000",
        "currency": "RUB",
        "payment_status": "paid",
    }
    signed = {**payload, "sign": make_2328_signature(payload, "secret")}

    assert verify_2328_webhook(signed, "secret") is True
    assert verify_2328_webhook({**signed, "amount": "1.00"}, "secret") is False


@pytest.mark.asyncio
async def test_2328_provider_packages_keep_card_rub_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"RUB":"326.09","USD":"6"}}}',
    )

    packages = await Payment2328Service.provider_packages()

    assert set(packages) == {"starter"}
    assert packages["starter"].credits == Decimal("300")
    assert packages["starter"].prices == {"RUB": Decimal("326.09"), "USD": Decimal("6")}


@pytest.mark.asyncio
async def test_2328_checkout_uses_local_payment_uuid_as_upstream_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"RUB":"326.09","USD":"6"}}}',
    )
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    monkeypatch.setattr(payment_2328_settings, "project_uuid", "project-uuid")
    monkeypatch.setattr(payment_2328_settings, "api_key", "secret")
    calls: list[dict[str, str]] = []

    async def fake_create_payment(
        self: Payment2328Client,
        *,
        local_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        callback_url: str,
    ) -> CreatedPayment:
        calls.append(
            {
                "local_id": local_id,
                "amount": str(amount),
                "currency": currency,
                "description": description,
                "callback_url": callback_url,
            }
        )
        return CreatedPayment(
            external_id="db17d490-15b6-47b9-9015-91d1d8b119f2",
            payment_url="https://go.2328.io/db17d490-15b6-47b9-9015-91d1d8b119f2",
            raw={
                "uuid": "db17d490-15b6-47b9-9015-91d1d8b119f2",
                "order_id": local_id,
                "payment_status": "check",
            },
        )

    async def fake_aclose(self: Payment2328Client) -> None:
        return None

    monkeypatch.setattr(Payment2328Client, "create_payment", fake_create_payment)
    monkeypatch.setattr(Payment2328Client, "aclose", fake_aclose)
    request_key = str(uuid.uuid4())

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="CryptoCheckout")
        session.add(user)
        await session.commit()

        first = await Payment2328Service.create(
            session,
            user_id=user.id,
            package_id="starter",
            request_key=request_key,
        )
        second = await Payment2328Service.create(
            session,
            user_id=user.id,
            package_id="starter",
            request_key=request_key,
        )

        assert first.id == second.id
        assert first.provider == "2328"
        assert first.amount == Decimal("326.09")
        assert first.currency == "RUB"
        assert first.rox_amount == Decimal("350")
        assert first.payload["base_credits"] == "300"
        assert first.payload["bonus_credits"] == "50"
        assert first.payload["payment_url"].startswith("https://go.2328.io/")
        assert calls == [
            {
                "local_id": str(first.id),
                "amount": "326.09",
                "currency": "RUB",
                "description": "Пополнение ROXY: 300 ROX",
                "callback_url": "https://roxy.example/webhooks/payments/2328",
            }
        ]


def test_2328_crypto_checkout_replaces_cryptobot_in_public_surfaces() -> None:
    api_source = Path("app/api/v1/payments.py").read_text(encoding="utf-8")
    wallet_source = Path("frontend/mini-app/components/wallet-parity.tsx").read_text(
        encoding="utf-8"
    )
    payments_source = Path("frontend/mini-app/app/payments/page.tsx").read_text(
        encoding="utf-8"
    )

    assert '@router.get("/crypto/packages")' in api_source
    assert '@router.post("/crypto/checkout"' in api_source
    assert '@router.post("/crypto/{payment_id}/reconcile")' in api_source
    assert 'Payment2328Service.PROVIDER' in api_source
    assert '"/api/v1/payments/crypto/packages"' in wallet_source
    assert '/mini-app/payments/?provider=2328' in wallet_source
    assert "Оплатить криптовалютой" in wallet_source
    assert '"/api/v1/payments/crypto/checkout"' in payments_source
    assert 'type Provider = "card" | "2328"' in payments_source
    assert "CryptoBot" not in wallet_source
    assert "CryptoBot" not in payments_source
