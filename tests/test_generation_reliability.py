import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Generation, User, Wallet
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.providers.kie import KieTask
from app.services.generation_provider import GenerationProviderService
from app.services.generation_reliability import GenerationOutboxService, retry_delay_seconds
from app.services.generation_worker import GenerationWorkerService
from app.services.generations import GenerationService
from app.services.wallet import WalletService


class BrokenWakeRedis:
    """Limiter works, but the post-commit best-effort wake signal fails."""

    async def eval(self, *_args: object, **_kwargs: object) -> list[int]:
        return [1, 60]

    async def rpush(self, *_args: object, **_kwargs: object) -> int:
        raise RedisError("redis unavailable after admission")


async def _create_user_with_wallet(first_name: str) -> tuple[User, Wallet]:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(5_000_000_000_000, 8_999_999_999_999),
            first_name=first_name,
        )
        session.add(user)
        await session.flush()
        wallet = await WalletService.ensure_wallet(session, user.id)
        await session.commit()
        return user, wallet


@pytest.mark.asyncio
async def test_generation_create_is_durable_when_redis_wakeup_fails() -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(2_000_000_000_000, 2_999_999_999_999),
            first_name="Outbox",
        )
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="test_credit",
            idempotency_key=f"reliability-credit:{user.id}",
        )
        await session.commit()

        generation = await GenerationService.create(
            session,
            BrokenWakeRedis(),  # type: ignore[arg-type]
            user_id=user.id,
            model_id="nano-banana",
            prompt="durable task",
        )

        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation.id)
        )
        wallet = await session.get(Wallet, user.id)
        assert outbox is not None
        assert outbox.status == "pending"
        assert wallet is not None
        assert generation.cost_rox == Decimal("80.00")
        assert wallet.balance == Decimal("20.00")

        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=False,
        )


@pytest.mark.asyncio
async def test_env_admin_generates_without_wallet_charge(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(9_000_000_000_000, 9_999_999_999_999),
            first_name="Free admin",
        )
        session.add(user)
        await session.flush()
        monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(user.telegram_id))
        await WalletService.ensure_wallet(session, user.id)
        await session.commit()

        generation = await GenerationService.create(
            session,
            BrokenWakeRedis(),  # type: ignore[arg-type]
            user_id=user.id,
            model_id="nano-banana",
            prompt="admin free task",
        )

        wallet = await session.get(Wallet, user.id)
        assert generation.cost_rox == Decimal("0.00")
        assert generation.parameters["_admin_free_generation"] is True
        assert generation.parameters["_quoted_cost_rox"] == "80.00"
        assert wallet is not None
        assert wallet.balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_outbox_claim_is_leased_and_reclaimable() -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(3_000_000_000_000, 3_999_999_999_999),
            first_name="Lease",
        )
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="queued",
            prompt="lease",
            cost_rox=Decimal("1"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        repaired = await GenerationOutboxService.ensure_missing(session)
        assert repaired >= 1
        row = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation.id)
        )
        assert row is not None
        row.created_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        row.updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await session.commit()

        claim = await GenerationOutboxService.claim(session)
        assert claim is not None
        assert claim.generation_id == generation.id
        assert claim.attempts == 1

        await GenerationOutboxService.release(
            session,
            claim.outbox_id,
            error="retry me",
            delay_seconds=1,
        )
        row = await session.get(GenerationOutbox, claim.outbox_id)
        assert row is not None
        assert row.status == "pending"
        assert row.lease_until is None
        assert row.last_error == "retry me"

        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=False,
        )


@pytest.mark.asyncio
async def test_kie_callback_can_bind_task_after_worker_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKieClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get_task(self, task_id: str) -> KieTask:
            return KieTask(
                task_id=task_id,
                state="success",
                result_urls=["https://example.invalid/result.png"],
            )

    monkeypatch.setattr("app.services.generation_provider.KieClient", FakeKieClient)

    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(4_000_000_000_000, 4_999_999_999_999),
            first_name="Callback",
        )
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="submitting",
            prompt="callback",
            cost_rox=Decimal("1"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        GenerationOutboxService.add(session, generation.id)
        await session.commit()

        recovered = await GenerationProviderService.sync_kie_task(
            session,
            task_id="task_recovered",
            generation_id=generation.id,
        )
        assert recovered is not None
        assert recovered.external_id == "task_recovered"
        assert recovered.status == "succeeded"
        assert recovered.result_url == "https://example.invalid/result.png"
        assert recovered.parameters.get("_provider_submitted_at")

        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation.id)
        )
        assert outbox is not None
        assert outbox.status == "completed"


@pytest.mark.asyncio
async def test_failed_generation_stays_terminal_after_late_success_and_refunds_once() -> None:
    user, _ = await _create_user_with_wallet("Terminal")

    async with SessionFactory() as session:
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="generating",
            prompt="late callback",
            cost_rox=Decimal("7"),
            provider="kie",
            external_id="task_late_success",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        GenerationOutboxService.add(session, generation.id)
        await session.commit()

        await GenerationProviderService.fail_and_refund(session, generation.id, "provider failed")
        await GenerationProviderService.fail_and_refund(session, generation.id, "duplicate failure")
        await GenerationProviderService.apply_kie_task(
            session,
            generation,
            KieTask(
                task_id="task_late_success",
                state="success",
                result_urls=["https://example.invalid/late.png"],
            ),
        )
        await session.refresh(generation)

        wallet = await session.get(Wallet, user.id)
        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation.id)
        )
        assert generation.status == "failed"
        assert generation.result_url is None
        assert wallet is not None
        assert wallet.balance == Decimal("7")
        assert outbox is not None
        assert outbox.status == "failed"


@pytest.mark.asyncio
async def test_kie_success_without_results_remains_recoverable() -> None:
    user, _ = await _create_user_with_wallet("EmptyResult")

    async with SessionFactory() as session:
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="generating",
            prompt="empty result",
            cost_rox=Decimal("2"),
            provider="kie",
            external_id="task_empty_result",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        await GenerationProviderService.apply_kie_task(
            session,
            generation,
            KieTask(
                task_id="task_empty_result",
                state="success",
                result_urls=[],
            ),
        )
        await session.refresh(generation)

        wallet = await session.get(Wallet, user.id)
        assert generation.status == "generating"
        assert generation.result_url is None
        assert generation.error is not None
        assert "without result URLs" in generation.error
        assert wallet is not None
        assert wallet.balance == Decimal("0")


@pytest.mark.asyncio
async def test_uncertain_create_task_timeout_does_not_refund_or_resubmit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutKieClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def create_task(self, **_kwargs: object) -> str:
            request = httpx.Request("POST", "https://api.kie.ai/api/v1/jobs/createTask")
            raise httpx.ReadTimeout("provider response timed out", request=request)

    monkeypatch.setattr("app.services.generation_provider.KieClient", TimeoutKieClient)
    user, _ = await _create_user_with_wallet("Uncertain")

    async with SessionFactory() as session:
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="queued",
            prompt="uncertain submit",
            cost_rox=Decimal("5"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        with pytest.raises(httpx.ReadTimeout):
            await GenerationProviderService.submit_kie(session, generation.id)
        await session.refresh(generation)

        wallet = await session.get(Wallet, user.id)
        assert generation.status == "submitting"
        assert generation.external_id is None
        assert generation.parameters.get("_submission_uncertain") is True
        assert generation.parameters.get("_submission_uncertain_at")
        assert wallet is not None
        assert wallet.balance == Decimal("0")


def test_submission_error_disposition_distinguishes_retryable_and_ambiguous_http() -> None:
    request = httpx.Request("POST", "https://api.kie.ai/api/v1/jobs/createTask")

    rate_limited = httpx.HTTPStatusError(
        "rate limited",
        request=request,
        response=httpx.Response(429, request=request),
    )
    validation = httpx.HTTPStatusError(
        "validation failed",
        request=request,
        response=httpx.Response(422, request=request),
    )
    provider_error = httpx.HTTPStatusError(
        "provider error",
        request=request,
        response=httpx.Response(500, request=request),
    )

    assert GenerationProviderService._submission_error_disposition(rate_limited) == "retryable"
    assert GenerationProviderService._submission_error_disposition(validation) == "permanent"
    assert GenerationProviderService._submission_error_disposition(provider_error) == "uncertain"


@pytest.mark.asyncio
async def test_generation_hard_timeout_refunds_old_task_but_not_recent_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_hard_timeout_seconds", 60)
    old_user, _ = await _create_user_with_wallet("HardTimeoutOld")
    recent_user, _ = await _create_user_with_wallet("HardTimeoutRecent")

    old_started = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_started = datetime.now(timezone.utc)
    old_created = datetime.now(timezone.utc) - timedelta(hours=1)

    async with SessionFactory() as session:
        expired = Generation(
            user_id=old_user.id,
            kind="text_to_image",
            status="generating",
            prompt="expired",
            cost_rox=Decimal("3"),
            provider="kie",
            external_id="task_hard_expired",
            parameters={
                "_model_id": "nano-banana",
                "_provider_submitted_at": old_started.isoformat(),
            },
        )
        recent = Generation(
            user_id=recent_user.id,
            kind="text_to_image",
            status="generating",
            prompt="recent provider submit",
            cost_rox=Decimal("4"),
            provider="kie",
            external_id="task_hard_recent",
            parameters={
                "_model_id": "nano-banana",
                "_provider_submitted_at": recent_started.isoformat(),
            },
        )
        session.add_all([expired, recent])
        await session.flush()
        expired.created_at = old_created
        recent.created_at = old_created
        await session.commit()
        expired_id = expired.id
        recent_id = recent.id

    await GenerationWorkerService._expire_stuck_generations()

    async with SessionFactory() as session:
        expired = await session.get(Generation, expired_id)
        recent = await session.get(Generation, recent_id)
        expired_wallet = await session.get(Wallet, old_user.id)
        recent_wallet = await session.get(Wallet, recent_user.id)

        assert expired is not None
        assert expired.status == "failed"
        assert expired.error is not None
        assert "hard lifetime" in expired.error
        assert expired_wallet is not None
        assert expired_wallet.balance == Decimal("3")

        assert recent is not None
        assert recent.status == "generating"
        assert recent_wallet is not None
        assert recent_wallet.balance == Decimal("0")


def test_retry_backoff_is_capped() -> None:
    assert retry_delay_seconds(1) == 2
    assert retry_delay_seconds(2) == 4
    assert retry_delay_seconds(20) == 256
