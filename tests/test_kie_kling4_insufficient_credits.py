"""KIE balance rejection must be certain, translated, and refunded once."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.kie import KieProviderError
from app.services.generation_provider import GenerationProviderService


@pytest.mark.asyncio
@pytest.mark.parametrize("original_sound", [True, False])
@pytest.mark.parametrize("charged", [True, False])
async def test_kie_insufficient_supplier_balance_is_clear_and_refunded_once(monkeypatch, original_sound, charged):
    generation_id = uuid.uuid4()
    params = {
        "_model_id": "kling-4.0",
        "video_urls": ["https://cdn.example/video.mp4"],
        "keep_original_sound": original_sound,
    }
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(parameters=params, cost_rox="100" if charged else "0"))
    refunded = AsyncMock()
    monkeypatch.setattr(GenerationProviderService, "fail_and_refund", refunded)
    disposition = await GenerationProviderService._record_submission_error(
        session, generation_id, KieProviderError("Kie createTask rejected: 'Credits insufficient'", code=402),
    )
    assert disposition == "permanent"
    refunded.assert_awaited_once()
    args = refunded.await_args.args
    assert args[1] == generation_id
    assert ("Оплаченные ROX возвращены" in args[2]) is charged
    assert ("ROX не списаны" in args[2]) is (not charged)
    assert "недостаточно кредитов" in args[2]
    assert ("Сохранить исходный звук" in args[2]) is original_sound


@pytest.mark.asyncio
async def test_kie_ambiguous_task_acceptance_is_not_relabelled_as_balance_failure(monkeypatch):
    generation_id = uuid.uuid4()
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=SimpleNamespace(
        status="submitting", parameters={}, updated_at=None, error=None,
    ))
    fail = AsyncMock()
    monkeypatch.setattr(GenerationProviderService, "fail_and_refund", fail)
    ambiguous = KieProviderError("Kie createTask returned task ID with error code 402")
    assert await GenerationProviderService._record_submission_error(session, generation_id, ambiguous) == "uncertain"
    fail.assert_not_awaited()
