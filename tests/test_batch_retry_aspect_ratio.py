from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.batches import _view
from app.core.config import settings
from app.db.models import Generation, User, Wallet
from app.db.session import SessionFactory
from app.services.batch_generation_core import BatchIdempotencyConflict, request_hash
from app.services.batch_recovery import BatchRecoveryService
from app.services.batch_repository import BatchRepository
from app.services.billing_access import BillingAccessService
from app.services.generation_batches import GenerationBatchService
from app.services.wallet import WalletService


def _legacy_job() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), model_id="nano-banana-pro", prompt="Edit the portrait",
        parameters={"aspect_ratio": "auto", "resolution": "1K"}, billing_seconds=None,
    )


@pytest.mark.parametrize("ratio", [None, "", "   ", "auto", "AUTO", "22:7"])
async def test_legacy_batch_retry_rejects_unselected_or_invalid_ratio_before_billing(
    monkeypatch: pytest.MonkeyPatch, ratio: str | None,
) -> None:
    job = _legacy_job()
    monkeypatch.setattr(BatchRepository, "load", AsyncMock(return_value=job))
    monkeypatch.setattr(BatchRepository, "rows", AsyncMock(return_value=[
        (SimpleNamespace(input_url="https://cdn.example/failed.jpg"), SimpleNamespace(status="failed")),
    ]))
    billing = AsyncMock(side_effect=AssertionError("Invalid retry must not reach billing"))
    monkeypatch.setattr(BillingAccessService, "decision", billing)
    with pytest.raises(ValueError, match="соотношение сторон|формат"):
        await BatchRecoveryService.quote(
            object(), user_id=uuid.uuid4(), batch_id=job.id, aspect_ratio=ratio,
        )
    billing.assert_not_awaited()
    assert job.parameters == {"aspect_ratio": "auto", "resolution": "1K"}


async def test_retry_quote_uses_explicit_ratio_only_for_failed_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import batch_recovery

    job = _legacy_job()
    monkeypatch.setattr(BatchRepository, "load", AsyncMock(return_value=job))
    monkeypatch.setattr(BatchRepository, "rows", AsyncMock(return_value=[
        (SimpleNamespace(input_url="https://cdn.example/failed.jpg"), SimpleNamespace(status="failed")),
        (SimpleNamespace(input_url="https://cdn.example/ready.jpg"), SimpleNamespace(status="succeeded")),
    ]))
    prepare = AsyncMock(wraps=batch_recovery.prepare_items)
    monkeypatch.setattr(batch_recovery, "prepare_items", prepare)
    monkeypatch.setattr(BillingAccessService, "decision", AsyncMock(return_value=SimpleNamespace(
        effective_cost=Decimal("20"), retail_cost=Decimal("20"), admin_free=False,
    )))
    quote = await BatchRecoveryService.quote(
        object(), user_id=uuid.uuid4(), batch_id=job.id, aspect_ratio="9:16",
    )
    assert quote["failed_count"] == 1
    assert prepare.await_args.kwargs["parameters"]["aspect_ratio"] == "9:16"
    assert prepare.await_args.kwargs["input_urls"] == ["https://cdn.example/failed.jpg"]
    assert job.parameters["aspect_ratio"] == "auto"


def test_retry_omits_only_an_inherited_auto_field_unsupported_by_the_model() -> None:
    job = _legacy_job()
    job.model_id = "grok-image-i2i"
    options = BatchRecoveryService.retry_options(job)
    assert options["aspect_ratio_options"] == []
    assert options["aspect_ratio_required"] is False
    assert "aspect_ratio" not in BatchRecoveryService._retry_parameters(job, None)
    assert job.parameters["aspect_ratio"] == "auto"
    with pytest.raises(ValueError, match="соотношение сторон"):
        BatchRecoveryService._retry_parameters(job, "9:16")


@pytest.mark.parametrize("request_parameters", [{}, {"aspect_ratio": None}])
async def test_old_no_body_retry_command_replays_before_new_ratio_policy(
    monkeypatch: pytest.MonkeyPatch, request_parameters: dict,
) -> None:
    job = _legacy_job()
    prior = SimpleNamespace(
        batch_id=job.id,
        request_hash=request_hash({"batch_id": str(job.id), "kind": "retry_failed"}),
        result_generation_ids=[str(uuid.uuid4())],
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=prior))
    monkeypatch.setattr(BatchRepository, "load", AsyncMock(return_value=job))
    rows = AsyncMock(side_effect=AssertionError("A replay must not prepare or bill another retry"))
    monkeypatch.setattr(BatchRepository, "rows", rows)
    replayed_job, replayed, count = await BatchRecoveryService.execute(
        session, object(), user_id=uuid.uuid4(), batch_id=job.id,
        idempotency_key="existing-retry-key", **request_parameters,
    )
    assert (replayed_job, replayed, count) == (job, True, 1)
    rows.assert_not_awaited()


async def test_retry_api_forwards_the_same_explicit_choice_to_quote_and_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.v1 import batches as api

    user = SimpleNamespace(id=uuid.uuid4())
    job = _legacy_job()
    quote = AsyncMock(return_value={"failed_count": 1})
    execute = AsyncMock(return_value=(job, False, 1))
    monkeypatch.setattr(BatchRecoveryService, "quote", quote)
    monkeypatch.setattr(BatchRecoveryService, "execute", execute)
    monkeypatch.setattr(api, "_view", AsyncMock(return_value={"id": str(job.id)}))
    await api.retry_quote(job.id, user, object(), aspect_ratio="9:16")
    await api.retry_batch(
        job.id, user, object(), object(), idempotency_key="same-choice-key",
        payload=api.BatchRetryRequest(aspect_ratio="9:16"),
    )
    assert quote.await_args.kwargs["aspect_ratio"] == "9:16"
    assert execute.await_args.kwargs["aspect_ratio"] == "9:16"


async def test_legacy_batch_retry_freezes_choice_and_replays_without_another_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Batch ratio test")
        session.add(user)
        await session.flush()
        await WalletService.credit(
            session, user_id=user.id, amount=Decimal("1000"), kind="test_seed",
            reference_type="test", reference_id=str(user.id),
            idempotency_key=f"batch-ratio-seed:{user.id}",
        )
        await session.commit()
        job, _ = await GenerationBatchService.create(
            session, AsyncMock(), user_id=user.id, model_id="nano-banana-pro",
            prompt="Edit both portraits", parameters={"aspect_ratio": "1:1"}, billing_seconds=None,
            input_urls=["https://cdn.example/portrait-a.jpg", "https://cdn.example/portrait-b.jpg"],
            reference_ids=[], idempotency_key=f"batch-ratio:{uuid.uuid4()}",
        )
        rows = await BatchRepository.rows(session, job.id)
        failed_item, old_generation = rows[0]
        # Represent a saved batch created before explicit ratios were required.
        job.parameters = {**job.parameters, "aspect_ratio": "auto"}
        old_generation.parameters = {**old_generation.parameters, "aspect_ratio": "auto"}
        old_generation.status = "failed"
        rows[1][1].status = "succeeded"
        await session.commit()
        old_generation_id = old_generation.id
        ready_generation_id = rows[1][1].id

        public = await _view(session, job)
        assert public["aspect_ratio_required"] is True
        assert public["default_aspect_ratio"] is None
        assert "9:16" in public["aspect_ratio_options"]
        assert "auto" not in public["aspect_ratio_options"]
        assert "aspect_ratio" not in public["parameters"]
        assert job.parameters["aspect_ratio"] == "auto"

        quote = await BatchRecoveryService.quote(
            session, user_id=user.id, batch_id=job.id, aspect_ratio="9:16",
        )
        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        balance_before = Decimal(wallet.balance)
        key = f"batch-ratio-retry:{uuid.uuid4()}"
        _, replayed, retried = await BatchRecoveryService.execute(
            session, AsyncMock(), user_id=user.id, batch_id=job.id,
            idempotency_key=key, aspect_ratio="9:16",
        )
        _, replayed_again, retried_again = await BatchRecoveryService.execute(
            session, AsyncMock(), user_id=user.id, batch_id=job.id,
            idempotency_key=key, aspect_ratio="9:16",
        )
        assert (replayed, retried, replayed_again, retried_again) == (False, 1, True, 1)
        with pytest.raises(BatchIdempotencyConflict):
            await BatchRecoveryService.execute(
                session, AsyncMock(), user_id=user.id, batch_id=job.id,
                idempotency_key=key, aspect_ratio="16:9",
            )
        await session.refresh(failed_item)
        replacement = await session.get(Generation, failed_item.generation_id)
        assert replacement is not None
        assert replacement.parent_generation_id == old_generation_id
        assert replacement.parameters["aspect_ratio"] == "9:16"
        assert job.parameters["aspect_ratio"] == "auto"
        assert old_generation.parameters["aspect_ratio"] == "auto"
        current_rows = await BatchRepository.rows(session, job.id)
        assert current_rows[1][1].id == ready_generation_id
        await session.refresh(wallet)
        assert Decimal(wallet.balance) == balance_before - Decimal(str(quote["total_cost_credits"]))


async def test_concurrent_same_key_retry_recovers_the_accepted_receipt_after_waiting_for_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Concurrent batch ratio")
        session.add(user)
        await session.flush()
        await WalletService.credit(
            session, user_id=user.id, amount=Decimal("1000"), kind="test_seed",
            reference_type="test", reference_id=str(user.id),
            idempotency_key=f"batch-ratio-race-seed:{user.id}",
        )
        await session.commit()
        job, _ = await GenerationBatchService.create(
            session, AsyncMock(), user_id=user.id, model_id="nano-banana-pro",
            prompt="Edit the portraits", parameters={"aspect_ratio": "1:1"}, billing_seconds=None,
            input_urls=["https://cdn.example/race-a.jpg", "https://cdn.example/race-b.jpg"],
            reference_ids=[], idempotency_key=f"batch-ratio-race:{uuid.uuid4()}",
        )
        rows = await BatchRepository.rows(session, job.id)
        job.parameters = {**job.parameters, "aspect_ratio": "auto"}
        rows[0][1].status = "failed"
        rows[1][1].status = "succeeded"
        await session.commit()
        user_id, batch_id = user.id, job.id
        failed_generation_id = rows[0][1].id
        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        balance_before = Decimal(wallet.balance)

    original_replay_check = BatchRecoveryService.replay_check
    both_initial_lookups_finished = asyncio.Event()
    initial_lookups = 0

    async def synchronized_replay_check(session, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal initial_lookups
        result = await original_replay_check(session, **kwargs)
        if result[0] is None and initial_lookups < 2:
            initial_lookups += 1
            if initial_lookups == 2:
                both_initial_lookups_finished.set()
            await asyncio.wait_for(both_initial_lookups_finished.wait(), timeout=10)
        return result

    monkeypatch.setattr(BatchRecoveryService, "replay_check", staticmethod(synchronized_replay_check))
    key = f"same-retry-command:{uuid.uuid4()}"

    async def execute():  # type: ignore[no-untyped-def]
        async with SessionFactory() as session:
            return await BatchRecoveryService.execute(
                session, AsyncMock(), user_id=user_id, batch_id=batch_id,
                idempotency_key=key, aspect_ratio="9:16",
            )

    results = await asyncio.wait_for(
        asyncio.gather(execute(), execute(), return_exceptions=True), timeout=30,
    )
    assert all(isinstance(result, tuple) for result in results), results
    assert sorted(result[1] for result in results) == [False, True]
    assert all(result[2] == 1 for result in results)
    async with SessionFactory() as session:
        rows = await BatchRepository.rows(session, batch_id)
        replacement = rows[0][1]
        assert rows[0][0].retry_count == 1
        assert replacement.parent_generation_id == failed_generation_id
        assert replacement.parameters["aspect_ratio"] == "9:16"
        wallet = await session.get(Wallet, user_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == balance_before - replacement.cost_rox
