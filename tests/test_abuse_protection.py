import random
import uuid
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.abuse_protection import (
    AbuseProtectionService,
    GenerationAdmissionService,
    ProtectionBackendUnavailable,
    ProviderCircuitOpen,
    ResourceLimitExceeded,
)


@pytest.mark.asyncio
async def test_fixed_window_rate_limit_uses_real_redis() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    key = f"test:rate:{uuid.uuid4()}"
    try:
        first = await AbuseProtectionService.consume(
            redis,
            key=key,
            limit=2,
            window_seconds=60,
        )
        second = await AbuseProtectionService.consume(
            redis,
            key=key,
            limit=2,
            window_seconds=60,
        )
        assert first.used == 1
        assert second.used == 2
        with pytest.raises(ResourceLimitExceeded) as exc_info:
            await AbuseProtectionService.consume(
                redis,
                key=key,
                limit=2,
                window_seconds=60,
            )
        assert exc_info.value.retry_after > 0
    finally:
        await redis.delete(key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_upload_daily_byte_quota_counts_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    user_id = uuid.uuid4()
    day_key_prefix = f"abuse:upload:bytes:{user_id}:"
    monkeypatch.setattr(settings, "upload_rate_limit_per_minute", 100)
    monkeypatch.setattr(settings, "upload_daily_bytes_limit", 10)
    try:
        await AbuseProtectionService.upload_rate_and_bytes(
            redis,
            user_id=user_id,
            size_bytes=6,
        )
        with pytest.raises(ResourceLimitExceeded):
            await AbuseProtectionService.upload_rate_and_bytes(
                redis,
                user_id=user_id,
                size_bytes=5,
            )
    finally:
        keys = [key async for key in redis.scan_iter(f"{day_key_prefix}*")]
        keys.extend([key async for key in redis.scan_iter(f"abuse:upload:req:{user_id}")])
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_generation_active_cap_is_serialized_in_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_max_active_per_user", 1)
    monkeypatch.setattr(settings, "generation_daily_spend_limit_credits", Decimal("0"))
    async with SessionFactory() as session:
        user = User(
            telegram_id=14_000_000_000_000 + random.randint(1, 999_999_999),
            first_name="Admission",
        )
        session.add(user)
        await session.flush()
        session.add(
            Generation(
                user_id=user.id,
                kind="text_to_image",
                status="generating",
                prompt="already active",
                cost_rox=Decimal("8"),
                provider="kie",
                parameters={"_model_id": "nano-banana"},
            )
        )
        await session.commit()

        with pytest.raises(ResourceLimitExceeded, match="active generations"):
            await GenerationAdmissionService.enforce(
                session,
                user_id=user.id,
                next_cost=Decimal("8"),
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_generation_daily_spend_limit_is_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_max_active_per_user", 0)
    monkeypatch.setattr(settings, "generation_daily_spend_limit_credits", Decimal("10"))
    async with SessionFactory() as session:
        user = User(
            telegram_id=15_000_000_000_000 + random.randint(1, 999_999_999),
            first_name="DailySpend",
        )
        session.add(user)
        await session.flush()
        session.add(
            Generation(
                user_id=user.id,
                kind="text_to_image",
                status="succeeded",
                prompt="spent today",
                cost_rox=Decimal("8"),
                provider="kie",
                parameters={"_model_id": "nano-banana"},
            )
        )
        await session.commit()

        with pytest.raises(ResourceLimitExceeded, match="Daily generation spend"):
            await GenerationAdmissionService.enforce(
                session,
                user_id=user.id,
                next_cost=Decimal("3"),
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_provider_failures_open_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    provider = f"kie-test-{uuid.uuid4()}"
    monkeypatch.setattr(settings, "kie_circuit_failure_threshold", 2)
    monkeypatch.setattr(settings, "kie_circuit_failure_window_seconds", 60)
    monkeypatch.setattr(settings, "kie_circuit_open_seconds", 30)
    monkeypatch.setattr(settings, "kie_submit_rate_limit_per_minute", 100)
    try:
        await AbuseProtectionService.record_provider_failure(redis, provider)
        await AbuseProtectionService.record_provider_failure(redis, provider)
        with pytest.raises(ProviderCircuitOpen) as exc_info:
            await AbuseProtectionService.provider_submission_gate(redis, provider)
        assert 1 <= exc_info.value.retry_after <= 30
    finally:
        await redis.delete(
            f"abuse:circuit:{provider}:failures",
            f"abuse:circuit:{provider}:open",
            f"abuse:provider-submit:{provider}",
        )
        await redis.aclose()


@pytest.mark.asyncio
async def test_expensive_mutation_fails_closed_when_protection_store_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRedis:
        async def eval(self, *_args: object, **_kwargs: object) -> object:
            raise RedisError("down")

    monkeypatch.setattr(settings, "abuse_fail_closed", True)
    with pytest.raises(ProtectionBackendUnavailable):
        await AbuseProtectionService.consume(
            BrokenRedis(),  # type: ignore[arg-type]
            key="test:down",
            limit=1,
            window_seconds=60,
        )
