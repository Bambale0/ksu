"""Authenticated Card refund/chargeback receipts: durable and zero-financial-effects."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.card_webhooks import router
from app.core.config import settings
from app.db.card_webhook_review_models import CardWebhookEventReview
from app.db.models import WalletTransaction
from app.db.session import SessionFactory
from app.services.card_payment_recovery import CardPaymentRecoveryService
from app.services.card_payments import CardPaymentService
from app.services.card_webhook_review import CardWebhookReviewService


def _payload(event_type: str, event_id: uuid.UUID) -> dict[str, Any]:
    # The documented Lava Top refund/chargeback envelope has no invoice ID.
    return {
        "event_type": event_type,
        "event_id": str(event_id),
        "created_at": "2026-11-16T09:01:02Z",
        "data": {
            "customer_email": "customer-private@example.invalid",
            "amount": 400,
            "currency": "EUR",
            "product": {"product_name": "private product"},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["refund.success", "chargeback.initiated"])
async def test_authenticated_card_review_webhook_is_durable_deduped_and_private(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, event_type: str,
) -> None:
    monkeypatch.setattr(settings, "card_webhook_key", "test-card-review-key")

    async def must_not_reconcile(*args: object, **kwargs: object) -> None:
        pytest.fail("Review events must never reconcile or settle a payment")

    monkeypatch.setattr(CardPaymentService, "reconcile", must_not_reconcile)
    monkeypatch.setattr(CardPaymentRecoveryService, "recover_missing_external_id", must_not_reconcile)

    event_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(router)

    async with SessionFactory() as session:
        before_reversals = (
            await session.execute(select(WalletTransaction.id))
        ).all()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        for _ in range(2):
            result = await client.post(
                "/webhooks/payments/card",
                headers={"X-Api-Key": "test-card-review-key"},
                json=_payload(event_type, event_id),
            )
            assert result.status_code == 200
            assert result.json() == {"ok": True}

    event_hash = hashlib.sha256(str(event_id).encode("ascii")).hexdigest()
    async with SessionFactory() as session:
        record = await session.get(CardWebhookEventReview, event_hash)
        assert record is not None
        assert record.event_type == event_type
        assert record.status == "manual_review"
        assert list((await session.scalars(
            select(CardWebhookEventReview).where(
                CardWebhookEventReview.event_id_hash == event_hash
            ),
        )).all()) == [record]
        assert (
            await session.execute(select(WalletTransaction.id))
        ).all() == before_reversals

    assert str(event_id) not in caplog.text
    assert "customer-private@example.invalid" not in caplog.text
    assert "private product" not in caplog.text


@pytest.mark.asyncio
async def test_refund_webhook_requires_provider_auth_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "card_webhook_key", "test-card-review-key")
    event_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post(
            "/webhooks/payments/card",
            headers={"X-Api-Key": "incorrect-key"},
            json=_payload("refund.success", event_id),
        )
    assert response.status_code == 403
    event_hash = hashlib.sha256(str(event_id).encode("ascii")).hexdigest()
    async with SessionFactory() as session:
        assert await session.get(CardWebhookEventReview, event_hash) is None


@pytest.mark.asyncio
async def test_card_review_bad_envelope_is_retryable_and_unknown_event_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "card_webhook_key", "test-card-review-key")
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        for bad in [
            {"event_type": "refund.success", "event_id": "not-a-uuid", "data": {}},
            {"event_type": "refund.success", "event_id": str(uuid.uuid4())},
            {"event_type": "chargeback.initiated", "data": {}},
        ]:
            response = await client.post(
                "/webhooks/payments/card",
                headers={"X-Api-Key": "test-card-review-key"},
                json=bad,
            )
            assert response.status_code == 400

        response = await client.post(
            "/webhooks/payments/card",
            headers={"X-Api-Key": "test-card-review-key"},
            json={"event_type": "future.unknown", "event_id": str(uuid.uuid4())},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_card_review_snapshot_is_aggregate_only() -> None:
    event_id = str(uuid.uuid4())
    async with SessionFactory() as session:
        assert await CardWebhookReviewService.record(
            session, event_type="refund.success", event_id=event_id,
        )
        snapshot = await CardWebhookReviewService.snapshot(session)
        assert any(
            row["event_type"] == "refund.success"
            and row["status"] == "manual_review"
            and row["count"] >= 1
            for row in snapshot
        )
        assert all(set(row) == {"event_type", "status", "count"} for row in snapshot)
        assert event_id not in repr(snapshot)
        assert all("email" not in str(row) for row in snapshot)
