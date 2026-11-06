from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.card_webhooks import router
from app.core.config import settings
from app.db.models import Payment, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError
from app.services.card_payments import CardPaymentService


async def _payment() -> Payment:
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Paid identity")
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id, provider="card", external_id=str(uuid.uuid4()),
            amount=Decimal("1087.00"), currency="RUB", rox_amount=Decimal("1000.00"),
            status="pending", payload={},
        )
        session.add(payment)
        await session.commit()
        return payment


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    payment: Payment,
    state: dict[str, Any],
) -> list[str]:
    """Replace transport only; exercise actual lookup/unwrapping and webhook auth."""
    calls: list[str] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.method == "GET"
        assert request.url.path == f"/api/v1/invoices/{payment.external_id}"
        if started := state.get("request_started"):
            started.set()
            await state["release_request"].wait()
        return httpx.Response(state.get("http_status", 200), json={"data": state["invoice"]})

    def init(
        self: CardCheckoutClient, api_key: str, base_url: str, webhook_key: str = "",
    ) -> None:
        self.api_key = "isolated-provider-key"
        self.base_url = "https://card.example.invalid"
        self.webhook_key = webhook_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url, transport=httpx.MockTransport(transport),
        )

    monkeypatch.setattr(CardCheckoutClient, "__init__", init)
    monkeypatch.setattr(settings, "card_webhook_key", "isolated-webhook-key")
    return calls


async def _webhook(payment: Payment) -> httpx.Response:
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        return await client.post(
            "/webhooks/payments/card",
            headers={"X-Api-Key": "isolated-webhook-key"},
            # Body money must never fill holes in authoritative invoice evidence.
            json={
                "eventType": "payment.success", "contractId": payment.external_id,
                "amount": "1087.00", "currency": "RUB",
            },
        )


async def _assert_no_credit(payment: Payment, *, status: str) -> Payment:
    async with SessionFactory() as session:
        stored = await session.get(Payment, payment.id)
        assert stored is not None
        assert stored.status == status
        assert stored.amount == Decimal("1087.00")
        assert stored.currency == "RUB"
        assert stored.external_id == payment.external_id
        assert await session.get(Wallet, payment.user_id) is None
        assert not list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == payment.user_id),
        )).all())
        return stored


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("money", "missing_id", "field"),
    [
        ({"receipt": {"currency": "RUB"}}, False, "amount"),
        ({"receipt": {"amount": "1087.00"}}, False, "currency"),
        ({"receipt": {}}, False, "amount"),
        ({"receipt": {"amount": "1087.00", "currency": "RUB"}}, True, "invoice id"),
        ({"amount": {"value": None}, "currency": "RUB"}, False, "amount"),
        ({"amount": "1087.00", "currency": {}}, False, "currency"),
        ({"receipt": {"amount": "sNaN", "currency": "RUB"}}, False, "amount"),
        ({"receipt": {"amount": "Infinity", "currency": "RUB"}}, False, "amount"),
        ({"receipt": {"amount": "1087.00", "currency": "ZZZ"}}, False, "currency"),
    ],
)
async def test_paid_webhook_rejects_missing_or_malformed_authoritative_identity(
    monkeypatch: pytest.MonkeyPatch,
    money: dict[str, Any],
    missing_id: bool,
    field: str,
) -> None:
    payment = await _payment()
    invoice = {"status": "COMPLETED", **money}
    if not missing_id:
        invoice["id"] = payment.external_id
    calls = _provider(monkeypatch, payment, {"invoice": invoice})

    response = await _webhook(payment)

    assert response.status_code == 502
    stored = await _assert_no_credit(payment, status="failed")
    assert stored.payload["invoice_integrity_error"]["field"] == field
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("money", [
    {"receipt": {"currency": "RUB"}},
    {"amountTotal": {"amount": "1087.00"}},
])
async def test_paid_poll_quarantines_sparse_invoice_without_credit(
    monkeypatch: pytest.MonkeyPatch,
    money: dict[str, Any],
) -> None:
    payment = await _payment()
    _provider(monkeypatch, payment, {"invoice": {
        "id": payment.external_id, "status": "PAID", **money,
    }})
    async with SessionFactory() as session:
        result = await CardPaymentService.reconcile(session, payment_id=payment.id)
        assert result.status == "failed"
    stored = await _assert_no_credit(payment, status="failed")
    assert "reconciliation_terminal_error" in stored.payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_status", "money", "expected_status"),
    [
        ("IN_PROGRESS", {"receipt": {"amount": "1087.00", "currency": "RUB"}}, "pending"),
        ("PENDING", {}, "pending"),
        ("", {"amount": "1087.00", "currency": "RUB"}, "pending"),
        ("FAILED", {"receipt": {"amount": "1087.00", "currency": "RUB"}}, "failed"),
    ],
)
async def test_success_event_waits_for_authoritative_paid_state_and_then_credits_once(
    monkeypatch: pytest.MonkeyPatch,
    provider_status: str,
    money: dict[str, Any],
    expected_status: str,
) -> None:
    payment = await _payment()
    state = {"invoice": {
        "id": payment.external_id, "status": provider_status, **money,
    }}
    calls = _provider(monkeypatch, payment, state)
    response = await _webhook(payment)
    assert response.status_code == 200
    stored = await _assert_no_credit(payment, status=expected_status)
    assert "invoice_integrity_error" not in stored.payload

    state["invoice"] = {
        "id": payment.external_id, "status": "COMPLETED",
        "receipt": {"amount": "1087.00", "currency": "RUB"},
    }
    assert (await _webhook(payment)).status_code == 200
    assert (await _webhook(payment)).status_code == 200
    async with SessionFactory() as session:
        stored = await session.get(Payment, payment.id)
        assert stored is not None and stored.status == "succeeded"
        wallet = await session.get(Wallet, payment.user_id)
        assert wallet is not None and wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == payment.user_id,
        ))).all())
        assert len(ledger) == 1
        assert ledger[0].idempotency_key == f"payment:{payment.id}:credit"
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"id": None},
    {"amount": None},
    {"currency": None},
    {"amount": "NaN"},
    {"amount": "1086.96"},
    {"currency": "USD"},
    {"status": "PENDING"},
])
async def test_direct_completion_cannot_bypass_paid_identity_guard(
    change: dict[str, Any],
) -> None:
    payment = await _payment()
    invoice = {
        "id": payment.external_id, "status": "PAID",
        "amount": "1087.00", "currency": "RUB", **change,
    }
    async with SessionFactory() as session:
        with pytest.raises(PaymentProviderError):
            await CardPaymentService.complete(
                session, payment_id=payment.id, provider_payload=invoice,
            )
    await _assert_no_credit(payment, status="pending")


@pytest.mark.asyncio
@pytest.mark.parametrize("money", [
    {"receipt": {"amount": "1087.00", "currency": "RUB"}},
    {"amountTotal": {"amount": "1087.00", "currency": "rub"}},
    {"amount": "1087.00", "currency": {"code": "RUB"}},
    {"amount": {"value": "1087.00", "currency": "RUB"}},
])
async def test_valid_money_shapes_allow_only_one_concurrent_completion(
    money: dict[str, Any],
) -> None:
    payment = await _payment()
    invoice = {"id": payment.external_id, "status": "COMPLETED", **money}

    async def settle() -> None:
        async with SessionFactory() as session:
            await CardPaymentService.complete(
                session, payment_id=payment.id, provider_payload=invoice,
            )

    await asyncio.gather(settle(), settle())
    async with SessionFactory() as session:
        wallet = await session.get(Wallet, payment.user_id)
        assert wallet is not None and wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == payment.user_id,
        ))).all())
        assert len(ledger) == 1
        assert ledger[0].idempotency_key == f"payment:{payment.id}:credit"


@pytest.mark.asyncio
@pytest.mark.parametrize("late_status", ["PAID", "PENDING", "FAILED"])
async def test_late_provider_state_preserves_manual_refund_review(late_status: str, monkeypatch) -> None:
    payment = await _payment()
    money = {"receipt": {"amount": "1087.00", "currency": "RUB"}}
    state = {"invoice": {"id": payment.external_id, "status": "PAID", **money}}
    _provider(monkeypatch, payment, state)
    assert (await _webhook(payment)).status_code == 200

    state["invoice"] = {"id": payment.external_id, "status": "REFUNDED", **money}
    async with SessionFactory() as session:
        reviewed = await CardPaymentService.reconcile(session, payment_id=payment.id)
        assert reviewed.status == "refund_review"

    state["invoice"] = {"id": payment.external_id, "status": late_status, **money}
    assert (await _webhook(payment)).status_code == 200
    assert (await _webhook(payment)).status_code == 200

    async with SessionFactory() as session:
        stored = await session.get(Payment, payment.id)
        assert stored is not None and stored.status == "refund_review"
        assert stored.payload["refund_review"] is True
        assert stored.payload["last_provider_state"]["status"] == "REFUNDED"
        wallet = await session.get(Wallet, payment.user_id)
        assert wallet is not None and wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == payment.user_id,
        ))).all())
        assert len(ledger) == 1
        assert ledger[0].idempotency_key == f"payment:{payment.id}:credit"


@pytest.mark.asyncio
@pytest.mark.parametrize("late_status", ["PENDING", "FAILED"])
async def test_delayed_lookup_cannot_overwrite_concurrently_settled_payment(
    late_status: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = await _payment()
    money = {"receipt": {"amount": "1087.00", "currency": "RUB"}}
    _provider(monkeypatch, payment, {"invoice": {
        "id": payment.external_id, "status": late_status, **money,
    }})
    original_lookup = CardCheckoutClient.get_invoice
    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()

    async def delayed_lookup(self: CardCheckoutClient, invoice_id: str) -> dict[str, Any]:
        invoice = await original_lookup(self, invoice_id)
        lookup_started.set()
        await release_lookup.wait()
        return invoice

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", delayed_lookup)
    pending_webhook = asyncio.create_task(_webhook(payment))
    try:
        await asyncio.wait_for(lookup_started.wait(), timeout=10)
        # Another transaction settles while the original webhook holds only its
        # stale ORM snapshot; the network wait must not hold the payment lock.
        async with SessionFactory() as session:
            await asyncio.wait_for(CardPaymentService.complete(
                session, payment_id=payment.id, provider_payload={
                    "id": payment.external_id, "status": "PAID", **money,
                },
            ), timeout=10)
    finally:
        release_lookup.set()
        response = await asyncio.wait_for(pending_webhook, timeout=10)
    assert response.status_code == 200

    async with SessionFactory() as session:
        stored = await session.get(Payment, payment.id)
        assert stored is not None and stored.status == "succeeded"
        assert stored.payload["last_provider_state"]["status"] == "PAID"
        wallet = await session.get(Wallet, payment.user_id)
        assert wallet is not None and wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == payment.user_id,
        ))).all())
        assert len(ledger) == 1
        assert ledger[0].idempotency_key == f"payment:{payment.id}:credit"


@pytest.mark.asyncio
@pytest.mark.parametrize("manual_review", [False, True], ids=["concurrent-paid", "refund-review"])
async def test_lookup_rejection_preserves_committed_payment_state(
    monkeypatch: pytest.MonkeyPatch, manual_review: bool,
) -> None:
    payment = await _payment()
    money = {"receipt": {"amount": "1087.00", "currency": "RUB"}}
    state = {"invoice": {"id": payment.external_id, "status": "PAID", **money}}
    _provider(monkeypatch, payment, state)
    if manual_review:
        assert (await _webhook(payment)).status_code == 200
        state["invoice"] = {"id": payment.external_id, "status": "REFUNDED", **money}
        async with SessionFactory() as session:
            reviewed = await CardPaymentService.reconcile(session, payment_id=payment.id)
            assert reviewed.status == "refund_review"

    state["http_status"] = 404
    state["invoice"] = {}
    started = asyncio.Event()
    release = asyncio.Event()
    state["request_started"] = started
    state["release_request"] = release
    pending_webhook = asyncio.create_task(_webhook(payment))
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        if not manual_review:
            async with SessionFactory() as session:
                await asyncio.wait_for(CardPaymentService.complete(
                    session, payment_id=payment.id, provider_payload={
                        "id": payment.external_id, "status": "PAID", **money,
                    },
                ), timeout=10)
    finally:
        release.set()
        response = await asyncio.wait_for(pending_webhook, timeout=10)
    assert response.status_code == 200

    async with SessionFactory() as session:
        stored = await session.get(Payment, payment.id)
        assert stored is not None
        assert stored.status == ("refund_review" if manual_review else "succeeded")
        assert "reconciliation_terminal_error" not in stored.payload
        assert stored.payload["last_provider_state"]["status"] == (
            "REFUNDED" if manual_review else "PAID"
        )
        wallet = await session.get(Wallet, payment.user_id)
        assert wallet is not None and wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == payment.user_id,
        ))).all())
        assert len(ledger) == 1
        assert ledger[0].idempotency_key == f"payment:{payment.id}:credit"
