from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import Payment, User
from app.db.payment_models import PaymentRequest
from app.db.session import SessionFactory
from app.providers.payment_2328 import (
    Payment2328Client,
    make_2328_signature,
    verify_2328_webhook,
)
from app.providers.payments import CreatedPayment, PaymentProviderError
from app.services.admin_security import utcnow
from app.services.payment_2328 import Payment2328Service


def _telegram_id() -> int:
    return 9_810_000_000_000 + random.randint(1, 999_999_999)


class _Missing2328Client:
    async def get_payment_info(
        self,
        *,
        external_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, object] | None:
        return None

    async def aclose(self) -> None:
        return None


class _ReconcileSession:
    def __init__(
        self,
        payment: Payment,
        request_row: PaymentRequest | None = None,
        *,
        locked_status: str | None = None,
    ) -> None:
        self.payment = payment
        self.request_row = request_row
        self.locked_status = locked_status
        self.commits = 0
        self.lock_reads = 0

    async def get(
        self,
        model: object,
        key: object,
        **kwargs: object,
    ) -> object | None:
        if model is Payment and key == self.payment.id:
            if kwargs.get("with_for_update"):
                self.lock_reads += 1
                if self.locked_status is not None:
                    self.payment.status = self.locked_status
            return self.payment
        return None

    async def scalar(self, statement: object) -> PaymentRequest | None:
        return self.request_row

    async def commit(self) -> None:
        self.commits += 1


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


def test_2328_is_hidden_without_public_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "payment_2328_project_uuid", "project-uuid")
    monkeypatch.setattr(settings, "payment_2328_api_key", "secret")
    monkeypatch.setattr(settings, "public_base_url", "")

    assert Payment2328Service.provider_configured() is False

    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    assert Payment2328Service.provider_configured() is True


@pytest.mark.asyncio
async def test_2328_client_refuses_invoice_without_callback() -> None:
    client = Payment2328Client("project-uuid", "secret")
    try:
        with pytest.raises(PaymentProviderError, match="callback URL"):
            await client.create_payment(
                local_id="ORDER-123",
                amount=Decimal("100.00"),
                currency="RUB",
                description="Пополнение ROXY",
                callback_url="",
            )
    finally:
        await client.aclose()


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
async def test_2328_recent_missing_payment_remains_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utcnow()
    payment = Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Payment2328Service.PROVIDER,
        external_id=None,
        amount=Decimal("326.09"),
        currency="RUB",
        rox_amount=Decimal("350"),
        status="creation_unknown",
        payload={"package_id": "starter"},
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=5),
    )
    session = _ReconcileSession(payment)

    monkeypatch.setattr(settings, "payment_2328_missing_grace_seconds", 2 * 60 * 60)
    monkeypatch.setattr(Payment2328Service, "_client", lambda: _Missing2328Client())

    result = await Payment2328Service.reconcile(session, payment_id=payment.id)

    assert result.status == "creation_unknown"
    assert "reconciliation_terminal_error" not in result.payload
    assert session.commits == 0


@pytest.mark.asyncio
async def test_2328_old_missing_payment_expires_after_recovery_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utcnow()
    payment = Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Payment2328Service.PROVIDER,
        external_id=f"missing-{uuid.uuid4()}",
        amount=Decimal("326.09"),
        currency="RUB",
        rox_amount=Decimal("350"),
        status="pending",
        payload={"package_id": "starter"},
        created_at=now - timedelta(hours=3),
        updated_at=now - timedelta(hours=3),
    )
    request_row = PaymentRequest(
        user_id=payment.user_id,
        payment_id=payment.id,
        request_key=str(uuid.uuid4()),
        provider=Payment2328Service.PROVIDER,
        package_id="starter",
        status="unknown",
    )
    session = _ReconcileSession(payment, request_row)

    monkeypatch.setattr(settings, "payment_2328_missing_grace_seconds", 2 * 60 * 60)
    monkeypatch.setattr(Payment2328Service, "_client", lambda: _Missing2328Client())

    result = await Payment2328Service.reconcile(session, payment_id=payment.id)

    assert result.status == "expired"
    assert result.payload["reconciliation_terminal_error"]["reason"] == (
        "provider_not_found_after_grace"
    )
    assert request_row.status == "failed"
    assert request_row.last_error
    assert session.lock_reads == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_2328_missing_provider_does_not_rewrite_terminal_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utcnow()
    payment = Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Payment2328Service.PROVIDER,
        external_id=f"gone-{uuid.uuid4()}",
        amount=Decimal("326.09"),
        currency="RUB",
        rox_amount=Decimal("350"),
        status="succeeded",
        payload={"package_id": "starter", "settled": True},
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    session = _ReconcileSession(payment)

    monkeypatch.setattr(settings, "payment_2328_missing_grace_seconds", 2 * 60 * 60)
    monkeypatch.setattr(Payment2328Service, "_client", lambda: _Missing2328Client())

    result = await Payment2328Service.reconcile(session, payment_id=payment.id)

    assert result.status == "succeeded"
    assert result.payload == {"package_id": "starter", "settled": True}
    assert session.lock_reads == 1
    assert session.commits == 0


@pytest.mark.asyncio
async def test_2328_webhook_terminal_state_wins_race_with_missing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utcnow()
    payment = Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=Payment2328Service.PROVIDER,
        external_id=f"gone-{uuid.uuid4()}",
        amount=Decimal("326.09"),
        currency="RUB",
        rox_amount=Decimal("350"),
        status="pending",
        payload={"package_id": "starter"},
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    session = _ReconcileSession(payment, locked_status="succeeded")

    monkeypatch.setattr(settings, "payment_2328_missing_grace_seconds", 2 * 60 * 60)
    monkeypatch.setattr(Payment2328Service, "_client", lambda: _Missing2328Client())

    result = await Payment2328Service.reconcile(session, payment_id=payment.id)

    assert result.status == "succeeded"
    assert "reconciliation_terminal_error" not in result.payload
    assert session.lock_reads == 1
    assert session.commits == 0


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
    monkeypatch.setattr(settings, "payment_2328_project_uuid", "project-uuid")
    monkeypatch.setattr(settings, "payment_2328_api_key", "secret")
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
        assert first.created_at.isoformat()
        assert first.updated_at.isoformat()
        assert calls == [
            {
                "local_id": str(first.id),
                "amount": "326.09",
                "currency": "RUB",
                "description": "Пополнение ROXY: 300 ROX",
                "callback_url": "https://roxy.example/webhooks/payments/2328",
            }
        ]
