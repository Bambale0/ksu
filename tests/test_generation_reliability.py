import random
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from app.db.models import Generation, User, Wallet
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.providers.kie import KieTask
from app.services.generation_provider import GenerationProviderService
from app.services.generation_reliability import GenerationOutboxService, retry_delay_seconds
from app.services.generations import GenerationService
from app.services.wallet import WalletService


class BrokenWakeRedis:
    async def rpush(self, *_args: object, **_kwargs: object) -> int:
        raise RedisError("redis unavailable")


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
        assert wallet.balance == Decimal("92.00")

        # Keep later queue-claim tests independent from this test's pending work.
        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=False,
        )


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
        # Force deterministic queue ordering even though the integration database is
        # shared by all tests in the CI job.
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

        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == generation.id)
        )
        assert outbox is not None
        assert outbox.status == "completed"


def test_retry_backoff_is_capped() -> None:
    assert retry_delay_seconds(1) == 2
    assert retry_delay_seconds(2) == 4
    assert retry_delay_seconds(20) == 256
