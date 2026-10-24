from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Payment, User, Wallet, WalletTransaction
from app.db.session import SessionFactory, engine
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import (
    CreatedPayment,
    PaymentProviderError,
    PaymentProviderValidationError,
)
from app.services.card_payments import CardPaymentService
from app.services.payment_reconciliation import PaymentReconciliationService


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", ["FAILED", "PAID", "PENDING"])
async def test_mismatched_card_invoice_stops_reconciliation_without_wallet_mutation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    provider_status: str,
) -> None:
    external_id = str(uuid.uuid4())
    calls = 0

    async def get_invoice(self: CardCheckoutClient, invoice_id: str) -> dict[str, Any]:
        nonlocal calls
        assert invoice_id == external_id
        calls += 1
        return {
            "id": external_id,
            "status": provider_status,
            "receipt": {"amount": 1086.96, "currency": "RUB"},
            "buyer": {"email": "private-buyer@example.invalid"},
        }

    monkeypatch.setattr(CardCheckoutClient, "get_invoice", get_invoice)
    monkeypatch.setattr(settings, "card_api_key", "test-key")
    monkeypatch.setattr(settings, "payment_reconcile_batch_size", 1)

    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Invoice integrity")
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id,
            provider="card",
            external_id=external_id,
            amount=Decimal("1087.00"),
            currency="RUB",
            rox_amount=Decimal("1000.00"),
            status="pending",
            payload={"package_id": "test-package"},
            updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        session.add(payment)
        await session.commit()

        assert await PaymentReconciliationService.run_once() == 1
        await session.refresh(payment)
        assert payment.status == "failed"
        assert payment.status not in PaymentReconciliationService.RECONCILABLE_STATUSES
        assert payment.amount == Decimal("1087.00")
        assert payment.external_id == external_id
        evidence = payment.payload["reconciliation_terminal_error"]
        assert evidence["reason"] == "invoice_amount_mismatch"
        assert payment.payload["invoice_integrity_error"] == {
            "field": "amount",
            "expected": "1087.00",
            "actual": "1086.96",
            "provider_status": provider_status.lower(),
        }
        assert not list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == user.id)
        )).all())
        assert calls == 1

    assert "card_invoice_integrity_mismatch" in caplog.text
    assert "private-buyer@example.invalid" not in caplog.text


@pytest.mark.asyncio
async def test_fixed_offer_price_mismatch_rejects_before_creating_remote_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr(settings, "card_packages_json", '''{
        "integrity": {"credits":"1000", "bonus_credits":"0",
        "prices":{"RUB":"1087.00"}, "offer_id":"fixed-integrity"}
    }''')

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        return {"items": [{"id": "product-integrity", "offers": [{
            "id": "fixed-integrity", "prices": [{"currency": "RUB", "amount": 1086.96}]
        }]}]}

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> None:
        pytest.fail("Known fixed-price mismatch must not create a payable invoice")

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)

    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Fixed offer mismatch")
        session.add(user)
        await session.commit()
        with pytest.raises(PaymentProviderValidationError, match="Цена"):
            await CardPaymentService.create(
                session,
                user_id=user.id,
                package_id="integrity",
                currency="RUB",
                billing_email="buyer@example.invalid",
                request_key=str(uuid.uuid4()),
            )
        payment = await session.scalar(select(Payment).where(Payment.user_id == user.id))
        assert payment is not None
        assert payment.status == "failed"
        assert payment.external_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned_amount", "evidence_amount"),
    [(1086.96, "1086.96"), ("invalid", "invalid"), ("NaN", "invalid"), ("sNaN", "invalid")],
)
async def test_changed_create_response_total_retains_invoice_and_blocks_checkout_replay(
    monkeypatch: pytest.MonkeyPatch,
    returned_amount: float | str,
    evidence_amount: str,
) -> None:
    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr(settings, "card_packages_json", '''{
        "integrity": {"credits":"1000", "bonus_credits":"0",
        "prices":{"RUB":"1087.00"}, "offer_id":"fixed-integrity"}
    }''')
    external_id = str(uuid.uuid4())
    calls = 0

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        return {"items": [{"offers": [{
            "id": "fixed-integrity", "prices": [{"currency": "RUB", "amount": 1087}]
        }]}]}

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
        nonlocal calls
        calls += 1
        return CreatedPayment(
            external_id=external_id,
            payment_url="https://pay.example.invalid/incorrect-price",
            raw={"data": {"id": external_id, "status": "new", "amountTotal": {
                "amount": returned_amount, "currency": "RUB",
            }}},
        )

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Changed invoice price")
        session.add(user)
        await session.commit()
        request = dict(
            user_id=user.id,
            package_id="integrity",
            currency="RUB",
            billing_email="buyer@example.invalid",
            request_key=str(uuid.uuid4()),
        )
        with pytest.raises(PaymentProviderValidationError, match="сумм"):
            await CardPaymentService.create(session, **request)
        replay = await CardPaymentService.create(session, **request)
        assert replay.external_id == external_id
        assert replay.status == "failed"
        assert replay.amount == Decimal("1087.00")
        assert not replay.payload.get("payment_url")
        assert replay.payload["invoice_integrity_error"]["actual"] == evidence_amount
        assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changed", "field"),
    [({"id": "different-contract"}, "invoice id"),
     ({"receipt": {"amount": 1087, "currency": "USD"}}, "currency")],
)
async def test_other_invoice_identity_mismatches_are_terminal_but_webhooks_still_reject(
    monkeypatch: pytest.MonkeyPatch,
    changed: dict[str, Any],
    field: str,
) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Invoice identity")
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id, provider="card", external_id=str(uuid.uuid4()),
            amount=Decimal("1087.00"), currency="RUB", rox_amount=Decimal("1000"),
            status="pending", payload={},
        )
        session.add(payment)
        await session.commit()

        async def get_invoice(self: CardCheckoutClient, invoice_id: str) -> dict[str, Any]:
            return {"id": invoice_id, "status": "PAID",
                    "receipt": {"amount": 1087, "currency": "RUB"}, **changed}

        monkeypatch.setattr(CardCheckoutClient, "get_invoice", get_invoice)
        with pytest.raises(PaymentProviderError, match="mismatch"):
            await CardPaymentService.reconcile(
                session, payment_id=payment.id, event_type="payment.success",
            )
        await session.refresh(payment)
        assert payment.status == "failed"
        assert payment.payload["invoice_integrity_error"]["field"] == field
        assert await session.scalar(select(Wallet).where(Wallet.user_id == user.id)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("refund_review", [False, True])
async def test_stale_mismatched_poll_cannot_overwrite_concurrently_settled_payment(
    monkeypatch: pytest.MonkeyPatch,
    refund_review: bool,
) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Concurrent settlement")
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id, provider="card", external_id=str(uuid.uuid4()),
            amount=Decimal("1087.00"), currency="RUB", rox_amount=Decimal("1000"),
            status="pending", payload={},
        )
        session.add(payment)
        await session.commit()

        first_lookup = True

        async def get_invoice(self: CardCheckoutClient, invoice_id: str) -> dict[str, Any]:
            nonlocal first_lookup
            if not first_lookup:
                return {"id": invoice_id, "status": "REFUNDED",
                        "receipt": {"amount": 1087, "currency": "RUB"}}
            first_lookup = False
            # The original session still holds the pending identity-map object.
            # A verified webhook commits while its earlier lookup is in flight.
            async with SessionFactory() as webhook_session:
                await CardPaymentService.complete(
                    webhook_session, payment_id=payment.id, provider_payload={"status": "paid"},
                )
                if refund_review:
                    await CardPaymentService.reconcile(webhook_session, payment_id=payment.id)
            return {"id": invoice_id, "status": "FAILED",
                    "receipt": {"amount": 1086.96, "currency": "RUB"}}

        monkeypatch.setattr(CardCheckoutClient, "get_invoice", get_invoice)
        result = await CardPaymentService.reconcile(session, payment_id=payment.id)
        assert result.status == ("refund_review" if refund_review else "succeeded")
        assert "invoice_integrity_error" not in result.payload
        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("1000.00")
        ledger = list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == user.id)
        )).all())
        assert len(ledger) == 1
        assert ledger[0].kind == "payment"


@pytest.mark.asyncio
async def test_valid_create_total_and_repeated_reconciliation_credit_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr(settings, "card_packages_json", '''{
        "integrity": {"credits":"1000", "bonus_credits":"0",
        "prices":{"RUB":"1087.00"}, "offer_id":"fixed-integrity"}
    }''')
    external_id = str(uuid.uuid4())

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        return {"items": [{"offers": [{"id": "fixed-integrity", "prices": [
            {"currency": "RUB", "amount": 1087}
        ]}]}]}

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
        assert kwargs["amount"] is None
        return CreatedPayment(
            external_id=external_id, payment_url="https://pay.example.invalid/valid",
            raw={"id": external_id, "amountTotal": {"amount": 1087, "currency": "RUB"}},
        )

    async def get_invoice(self: CardCheckoutClient, invoice_id: str) -> dict[str, Any]:
        return {"id": invoice_id, "status": "PAID",
                "receipt": {"amount": 1087, "currency": "RUB"}}

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
    monkeypatch.setattr(CardCheckoutClient, "get_invoice", get_invoice)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Valid invoice")
        session.add(user)
        await session.commit()
        payment = await CardPaymentService.create(
            session, user_id=user.id, package_id="integrity", currency="RUB",
            billing_email="buyer@example.invalid", request_key=str(uuid.uuid4()),
        )
        assert payment.status == "pending"
        for _ in range(2):
            await CardPaymentService.reconcile(session, payment_id=payment.id)
        assert payment.status == "succeeded"
        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("1000.00")
        assert len(list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == user.id)
        )).all())) == 1


@pytest.mark.asyncio
async def test_concurrent_checkout_replay_never_exposes_unvalidated_invoice_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr(settings, "card_packages_json", '''{
        "integrity": {"credits":"1000", "bonus_credits":"0",
        "prices":{"RUB":"1087.00"}, "offer_id":"fixed-integrity"}
    }''')
    external_id = str(uuid.uuid4())
    bound = asyncio.Event()
    resume = asyncio.Event()
    calls = 0

    class PausingCommitSession(AsyncSession):
        async def commit(self) -> None:
            await super().commit()
            if self.info.get("binding_paused"):
                return
            if any(isinstance(item, Payment) and item.external_id == external_id
                   for item in self.identity_map.values()):
                self.info["binding_paused"] = True
                bound.set()
                await resume.wait()

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        return {"items": [{"offers": [{"id": "fixed-integrity"}]}]}

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
        nonlocal calls
        calls += 1
        return CreatedPayment(
            external_id=external_id, payment_url="https://pay.example.invalid/unsafe",
            raw={"id": external_id, "amountTotal": {"amount": 1086.96, "currency": "RUB"}},
        )

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Concurrent replay")
        session.add(user)
        await session.commit()
        request = dict(
            user_id=user.id, package_id="integrity", currency="RUB",
            billing_email="buyer@example.invalid", request_key=str(uuid.uuid4()),
        )
    async with PausingCommitSession(bind=engine, expire_on_commit=False) as admission:
        creation = asyncio.create_task(CardPaymentService.create(admission, **request))
        try:
            await asyncio.wait_for(bound.wait(), timeout=10)
            async with SessionFactory() as replay_session:
                replay = await CardPaymentService.create(replay_session, **request)
                assert replay.external_id == external_id
                assert not replay.payload.get("payment_url")
                assert calls == 1
        finally:
            resume.set()
            with pytest.raises(PaymentProviderValidationError):
                await creation
