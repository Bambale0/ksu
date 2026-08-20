from __future__ import annotations

import random
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Payment, User
from app.db.payment_models import PaymentRequest
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError
from app.services.card_payment_recovery import CardPaymentRecoveryService


def _telegram_id() -> int:
    return 99_000_000_000_000 + random.randint(1, 999_999_999)


def _unknown_payment(user_id: uuid.UUID, *, email: str = "buyer@example.com") -> Payment:
    return Payment(
        user_id=user_id,
        provider="card",
        amount=Decimal("6.00"),
        currency="USD",
        rox_amount=Decimal("300.00"),
        status="creation_unknown",
        payload={
            "package_id": "starter",
            "billing_email": email,
        },
    )


@pytest.mark.asyncio
async def test_card_get_invoice_uses_current_single_contract_route() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "id": "contract-1",
                "amount": 6,
                "currency": "USD",
                "buyer": {"email": "buyer@example.com"},
            },
        )

    client = CardCheckoutClient("api-key", "https://example.invalid")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        invoice = await client.get_invoice("contract-1")
    finally:
        await client.aclose()

    assert seen == ["/api/v1/invoices/contract-1"]
    assert CardCheckoutClient.extract_invoice_id(invoice) == "contract-1"
    assert CardCheckoutClient.extract_buyer_email(invoice) == "buyer@example.com"


@pytest.mark.asyncio
async def test_lost_card_create_response_recovers_unique_unknown_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_id = f"contract-{uuid.uuid4()}"

    async def fake_get_invoice(
        self: CardCheckoutClient,
        invoice_id: str,
    ) -> dict[str, object]:
        assert invoice_id == contract_id
        return {
            "id": contract_id,
            "amount": "6.00",
            "currency": "USD",
            "buyer": {"email": "BUYER@example.com"},
            "status": "pending",
        }

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", fake_get_invoice)

    async with SessionFactory() as session:
        buyer = User(telegram_id=_telegram_id(), first_name="Card recover")
        session.add(buyer)
        await session.flush()

        payment = _unknown_payment(buyer.id)
        session.add(payment)
        await session.flush()
        request_row = PaymentRequest(
            user_id=buyer.id,
            payment_id=payment.id,
            request_key=str(uuid.uuid4()),
            provider="card",
            package_id="starter",
            status="unknown",
            last_error="create response lost",
        )
        session.add(request_row)
        await session.commit()
        payment_id = payment.id
        request_id = request_row.id

        recovered = await CardPaymentRecoveryService.recover_missing_external_id(
            session,
            external_id=contract_id,
        )
        request_row = await session.get(PaymentRequest, request_id)

        assert recovered.id == payment_id
        assert recovered.external_id == contract_id
        assert recovered.status == "pending"
        assert recovered.payload["recovered_external_id"] is True
        assert recovered.payload["recovery_source"] == "authoritative_invoice"
        assert request_row is not None
        assert request_row.status == "completed"
        assert request_row.last_error is None

        repeated = await CardPaymentRecoveryService.recover_missing_external_id(
            session,
            external_id=contract_id,
        )
        assert repeated.id == payment_id


@pytest.mark.asyncio
async def test_card_recovery_refuses_buyer_email_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_id = f"contract-{uuid.uuid4()}"

    async def fake_get_invoice(
        self: CardCheckoutClient,
        invoice_id: str,
    ) -> dict[str, object]:
        return {
            "id": invoice_id,
            "amount": "6.00",
            "currency": "USD",
            "buyer": {"email": "someone-else@example.com"},
        }

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", fake_get_invoice)

    async with SessionFactory() as session:
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer mismatch")
        session.add(buyer)
        await session.flush()
        payment = _unknown_payment(buyer.id)
        session.add(payment)
        await session.commit()
        payment_id = payment.id

        with pytest.raises(LookupError, match="not found"):
            await CardPaymentRecoveryService.recover_missing_external_id(
                session,
                external_id=contract_id,
            )

        payment = await session.get(Payment, payment_id)
        assert payment is not None
        assert payment.external_id is None
        assert payment.status == "creation_unknown"


@pytest.mark.asyncio
async def test_card_recovery_refuses_ambiguous_identical_unknown_intents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_id = f"contract-{uuid.uuid4()}"

    async def fake_get_invoice(
        self: CardCheckoutClient,
        invoice_id: str,
    ) -> dict[str, object]:
        return {
            "id": invoice_id,
            "amount": "6.00",
            "currency": "USD",
            "buyer": {"email": "same@example.com"},
        }

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", fake_get_invoice)

    async with SessionFactory() as session:
        first = User(telegram_id=_telegram_id(), first_name="First")
        second = User(telegram_id=_telegram_id(), first_name="Second")
        session.add_all([first, second])
        await session.flush()
        payment_a = _unknown_payment(first.id, email="same@example.com")
        payment_b = _unknown_payment(second.id, email="same@example.com")
        session.add_all([payment_a, payment_b])
        await session.commit()
        ids = (payment_a.id, payment_b.id)

        with pytest.raises(PaymentProviderError, match="ambiguous"):
            await CardPaymentRecoveryService.recover_missing_external_id(
                session,
                external_id=contract_id,
            )

        rows = list(
            (
                await session.scalars(select(Payment).where(Payment.id.in_(ids)))
            ).all()
        )
        assert len(rows) == 2
        assert all(row.external_id is None for row in rows)


@pytest.mark.asyncio
async def test_card_recovery_requires_authoritative_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_id = f"contract-{uuid.uuid4()}"

    async def fake_get_invoice(
        self: CardCheckoutClient,
        invoice_id: str,
    ) -> dict[str, object]:
        return {
            "id": invoice_id,
            "amount": "6.00",
            "currency": "USD",
        }

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", fake_get_invoice)

    async with SessionFactory() as session:
        buyer = User(telegram_id=_telegram_id(), first_name="Missing identity")
        session.add(buyer)
        await session.flush()
        session.add(_unknown_payment(buyer.id))
        await session.commit()

        with pytest.raises(PaymentProviderError, match="identity fields"):
            await CardPaymentRecoveryService.recover_missing_external_id(
                session,
                external_id=contract_id,
            )
