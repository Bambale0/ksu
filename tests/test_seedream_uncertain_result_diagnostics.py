"""Retain the real Seedream gateway rejection when an uncertain KSU image submit expires."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Generation, User, WalletTransaction
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.services.generation_reliability import ClaimedGeneration, GenerationOutboxService
from app.services.generation_worker import GenerationWorkerService


def _row(*, error_code: str = "provider_response_invalid", provider: str = "neironych"):
    return SimpleNamespace(
        parameters={
            "_model_id": "seedream-5-pro-i2i",
            "_provider_response": {
                "provider": provider,
                "http_status": 503,
                "error_code": error_code,
                "request_id": "private-diagnostic-request-id",
            },
        }
    )


def test_gateway_invalid_image_response_is_not_misreported_as_worker_interruption():
    message = GenerationWorkerService._unknown_submission_failure_reason(
        _row(), "neironych"
    )
    assert "результат изображения" in message
    assert "worker interruption" not in message
    assert "private-diagnostic-request-id" not in message


@pytest.mark.parametrize(
    "gateway_provider,code,provider",
    [
        ("other", "provider_response_invalid", "neironych"),
        ("neironych", "content_policy_violation", "neironych"),
        ("neironych", "provider_response_invalid", "kie"),
    ],
)
def test_unverified_or_unrelated_error_never_becomes_image_result_failure(
    gateway_provider, code, provider
):
    message = GenerationWorkerService._unknown_submission_failure_reason(
        _row(error_code=code, provider=gateway_provider), provider
    )
    assert "результат изображения" not in message
    assert "worker interruption" in message


@pytest.mark.asyncio
async def test_uncertain_seedream_result_timeout_preserves_original_receipt_and_refund_semantics(monkeypatch):
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(6_000_000_000_000, 7_999_999_999_999),
            first_name="Seedream result diagnostic regression",
        )
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="image_to_image",
            status="submitting",
            prompt="A clean studio portrait",
            provider="neironych",
            cost_rox=Decimal("0"),
            parameters={
                **_row().parameters,
                "_provider_route": ["neironych", "kie", "nexus"],
                "_provider_route_index": 0,
                "_submission_uncertain": True,
            },
        )
        session.add(generation)
        await session.flush()
        generation_id = generation.id
        outbox = GenerationOutboxService.add(session, generation_id)
        await session.flush()
        outbox_id = outbox.id
        generation.updated_at = datetime.now(timezone.utc) - timedelta(
            seconds=settings.generation_submission_unknown_timeout_seconds + 60
        )
        await session.commit()

    async def claim_our_generation(_session):
        # CI runs a full suite in the same test DB; do not claim another test's outbox.
        return ClaimedGeneration(outbox_id=outbox_id, generation_id=generation_id, attempts=1)

    monkeypatch.setattr(GenerationOutboxService, "claim", claim_our_generation)
    assert await GenerationWorkerService.process_one(None) is True  # type: ignore[arg-type]

    async with SessionFactory() as session:
        result = await session.get(Generation, generation_id)
        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation_id)
        )
        txns = list(
            await session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.reference_id == str(generation_id)
                )
            )
        )
        assert result is not None and result.status == "failed"
        assert result.provider == "neironych" and result.external_id is None
        assert result.parameters["_provider_response"]["error_code"] == "provider_response_invalid"
        assert "результат изображения" in (result.error or "")
        assert "worker interruption" not in (result.error or "")
        assert outbox is not None and outbox.status == "failed"
        assert not txns
