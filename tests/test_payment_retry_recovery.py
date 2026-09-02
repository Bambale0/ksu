from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.api.v1.payments import _payment_view
from app.db.models import Payment
from app.services.payment_2328 import Payment2328Service
from app.services.payments import PaymentService


class _Session:
    def __init__(self, payment: Payment) -> None:
        self.payment = payment
        self.commits = 0

    async def get(self, model: object, payment_id: uuid.UUID) -> Payment | None:
        if model is Payment and payment_id == self.payment.id:
            return self.payment
        return None

    async def scalar(self, statement: object) -> object | None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def _payment(*, provider: str, status: str = "creation_unknown") -> Payment:
    now = datetime.now(timezone.utc)
    return Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider=provider,
        external_id=None,
        amount=Decimal("326.09"),
        currency="RUB",
        rox_amount=Decimal("350"),
        status=status,
        payload={"package_id": "starter", "request_key": str(uuid.uuid4())},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_cryptobot_reconcile_restores_checkout_url_after_lost_create_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment(provider="cryptobot")
    session = _Session(payment)

    class _CryptoPayClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def find_invoice_by_payload(self, local_id: str) -> dict[str, object]:
            assert local_id == str(payment.id)
            return {
                "invoice_id": 998877,
                "payload": str(payment.id),
                "amount": "326.09",
                "fiat": "RUB",
                "status": "active",
                "mini_app_invoice_url": "https://t.me/CryptoBot?start=invoice-recovered",
            }

        async def get_invoice(self, external_id: str) -> dict[str, object] | None:
            raise AssertionError(f"unexpected external id lookup: {external_id}")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.services.payments.CryptoPayClient", _CryptoPayClient)

    result = await PaymentService.reconcile(session, payment_id=payment.id)

    assert result.external_id == "998877"
    assert result.status == "pending"
    assert _payment_view(result)["payment_url"] == (
        "https://t.me/CryptoBot?start=invoice-recovered"
    )
    assert session.commits == 1


@pytest.mark.asyncio
async def test_2328_reconcile_state_restores_checkout_url_after_lost_create_response() -> None:
    payment = _payment(provider="2328")
    session = _Session(payment)

    result = await Payment2328Service.apply_state(
        session,
        payment=payment,
        provider_payload={
            "uuid": "db17d490-15b6-47b9-9015-91d1d8b119f2",
            "order_id": str(payment.id),
            "amount": "326.09",
            "currency": "RUB",
            "payment_status": "check",
            "url": "https://go.2328.io/db17d490-15b6-47b9-9015-91d1d8b119f2",
        },
    )

    assert result.external_id == "db17d490-15b6-47b9-9015-91d1d8b119f2"
    assert result.status == "pending"
    assert _payment_view(result)["payment_url"] == (
        "https://go.2328.io/db17d490-15b6-47b9-9015-91d1d8b119f2"
    )
    assert session.commits == 1
