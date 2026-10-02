"""Fast regressions for slow synchronous image outages; no network or database I/O."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.abuse_protection import AbuseProtectionService, ProviderCircuitOpen


class ClockRedis:
    """Clock-controlled Redis seam implementing only the two existing Lua contracts."""

    def __init__(self) -> None:
        self.now = 0
        self.values: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def advance(self, seconds: int) -> None:
        self.now += seconds
        for key, deadline in list(self.expires.items()):
            if deadline <= self.now:
                self.values.pop(key, None)
                self.expires.pop(key, None)

    async def ttl(self, key: str) -> int:
        if key not in self.values:
            return -2
        return self.expires.get(key, self.now - 1) - self.now

    async def delete(self, *keys: str) -> int:
        count = sum(key in self.values for key in keys)
        for key in keys:
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return count

    async def eval(self, script: str, count: int, *args: object) -> list[int]:
        if script == AbuseProtectionService.CIRCUIT_FAILURE_LUA:
            assert count == 2
            failure_key, open_key, window, threshold, cooldown = args
            assert isinstance(failure_key, str) and isinstance(open_key, str)
            failures = self.values.get(failure_key, 0) + 1
            self.values[failure_key] = failures
            if failures == 1:
                self.expires[failure_key] = self.now + int(window)
            if failures >= int(threshold):
                self.values[open_key] = 1
                self.expires[open_key] = self.now + int(cooldown)
            return [failures, await self.ttl(open_key)]
        assert script == AbuseProtectionService.RATE_LUA and count == 1
        key, amount, window = args
        assert isinstance(key, str)
        value = self.values.get(key, 0) + int(amount)
        self.values[key] = value
        if value == int(amount):
            self.expires[key] = self.now + int(window)
        return [value, await self.ttl(key)]


@pytest.mark.asyncio
async def test_slow_image_failures_trip_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "kie_circuit_failure_threshold", 3)
    monkeypatch.setattr(settings, "kie_circuit_failure_window_seconds", 60)
    redis = ClockRedis()
    for _ in range(3):
        redis.advance(126)
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    with pytest.raises(ProviderCircuitOpen):
        await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")


@pytest.mark.asyncio
async def test_video_success_cannot_clear_image_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "kie_circuit_failure_threshold", 3)
    redis = ClockRedis()
    for _ in range(3):
        redis.advance(126)
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
        await AbuseProtectionService.record_provider_success(redis, "neironych")
    with pytest.raises(ProviderCircuitOpen):
        await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    await AbuseProtectionService.provider_submission_gate(redis, "neironych")


@pytest.mark.asyncio
async def test_scoped_image_rate_limit_stays_provider_wide(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.abuse_protection import ResourceLimitExceeded

    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "kie_submit_rate_limit_per_minute", 1)
    redis = ClockRedis()
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    with pytest.raises(ResourceLimitExceeded):
        await AbuseProtectionService.provider_submission_gate(redis, "neironych")


def test_worker_uses_image_scope_without_changing_provider() -> None:
    from types import SimpleNamespace
    from app.services.generation_worker import GenerationWorkerService

    image = SimpleNamespace(parameters={"_model_id": "nano-banana-pro"})
    video = SimpleNamespace(parameters={"_model_id": "seedance-2.5"})
    assert GenerationWorkerService._protection_provider(image, "neironych") == "neironych:image"
    assert GenerationWorkerService._protection_provider(video, "neironych") == "neironych"
    assert GenerationWorkerService._protection_provider(image, "nexus") == "nexus"


@pytest.mark.asyncio
async def test_image_cooldown_expires_but_late_success_does_not_close_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 2)
    monkeypatch.setattr(settings, "neironych_image_circuit_open_seconds", 17)
    redis = ClockRedis()
    for _ in range(2):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    await AbuseProtectionService.record_provider_success(redis, "neironych:image")
    redis.advance(16)
    with pytest.raises(ProviderCircuitOpen) as exc:
        await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    assert exc.value.retry_after == 1
    redis.advance(1)
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")


@pytest.mark.asyncio
async def test_image_failure_window_and_threshold_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 4)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_window_seconds", 30)
    redis = ClockRedis()
    for _ in range(4):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
        redis.advance(31)
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    for _ in range(4):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    with pytest.raises(ProviderCircuitOpen):
        await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")


@pytest.mark.asyncio
async def test_image_success_resets_only_its_own_failure_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 3)
    redis = ClockRedis()
    for _ in range(2):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    await AbuseProtectionService.record_provider_failure(redis, "neironych")
    await AbuseProtectionService.record_provider_success(redis, "neironych:image")
    await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    assert redis.values["abuse:circuit:neironych:image:failures"] == 1
    assert redis.values["abuse:circuit:neironych:failures"] == 1
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")


@pytest.mark.asyncio
async def test_disabled_image_failure_counter_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 0)
    redis = ClockRedis()
    for _ in range(6):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    assert not redis.values
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    before = dict(redis.values)
    await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    await AbuseProtectionService.provider_submission_gate(redis, "neironych:image")
    assert redis.values == before


@pytest.mark.asyncio
async def test_image_protection_redis_outage_remains_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from redis.exceptions import RedisError
    from app.services.abuse_protection import ProtectionBackendUnavailable

    class BrokenRedis:
        async def ttl(self, key: str) -> int:
            raise RedisError("unavailable")

    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "abuse_fail_closed", True)
    with pytest.raises(ProtectionBackendUnavailable):
        await AbuseProtectionService.provider_submission_gate(BrokenRedis(), "neironych:image")


@pytest.mark.asyncio
async def test_scoped_policy_uses_real_redis_atomic_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    import uuid
    from redis.asyncio import Redis

    scope = f"test:neironych:image:{uuid.uuid4()}"
    monkeypatch.setattr(AbuseProtectionService, "NEIRONYCH_IMAGE_CIRCUIT", scope)
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 2)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_window_seconds", 42)
    monkeypatch.setattr(settings, "neironych_image_circuit_open_seconds", 7)
    monkeypatch.setattr(settings, "kie_submit_rate_limit_per_minute", 0)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    failure_key, open_key = f"abuse:circuit:{scope}:failures", f"abuse:circuit:{scope}:open"
    try:
        await asyncio.gather(*(AbuseProtectionService.record_provider_failure(redis, scope) for _ in range(3)))
        assert await redis.get(failure_key) == "3"
        assert 1 <= await redis.ttl(failure_key) <= 42
        with pytest.raises(ProviderCircuitOpen) as exc:
            await AbuseProtectionService.provider_submission_gate(redis, scope)
        assert 1 <= exc.value.retry_after <= 7
    finally:
        await redis.delete(failure_key, open_key)
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [False, True])
async def test_worker_open_image_circuit_only_falls_back_before_submit(
    monkeypatch: pytest.MonkeyPatch, uncertain: bool,
) -> None:
    import uuid
    from decimal import Decimal
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.db.models import Generation, User
    from app.db.session import SessionFactory
    from app.services.generation_reliability import GenerationOutboxService
    from app.services.generation_worker import GenerationWorkerService
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.nexus_generation_provider import NexusGenerationProviderService

    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "neironych_image_circuit_failure_threshold", 2)
    async with SessionFactory() as session:
        user = User(telegram_id=32_000_000_000_000 + uuid.uuid4().int % 1_000_000_000, first_name="Circuit regression")
        session.add(user)
        await session.flush()
        parameters = {
            "_model_id": "nano-banana-pro", "_provider_route": ["neironych", "nexus"],
            "_provider_route_index": 0,
        }
        if uncertain:
            parameters["_submission_uncertain"] = True
        generation = Generation(
            user_id=user.id, kind="text_to_image", status="submitting" if uncertain else "queued",
            provider="neironych", prompt="test", cost_rox=Decimal("0"), parameters=parameters,
        )
        session.add(generation)
        await session.commit()
        generation_id = generation.id
    claim = SimpleNamespace(generation_id=generation_id, outbox_id=uuid.uuid4(), attempts=1)
    monkeypatch.setattr(GenerationOutboxService, "claim", AsyncMock(return_value=claim))
    release = AsyncMock()
    monkeypatch.setattr(GenerationOutboxService, "release", release)
    forbidden_submit = AsyncMock(side_effect=AssertionError("No paid POST is permitted in this scenario"))
    monkeypatch.setattr(NeironychGenerationProviderService, "submit", forbidden_submit)
    monkeypatch.setattr(NexusGenerationProviderService, "submit", forbidden_submit)
    redis = ClockRedis()
    for _ in range(2):
        await AbuseProtectionService.record_provider_failure(redis, "neironych:image")
    assert await GenerationWorkerService.process_one(redis)
    forbidden_submit.assert_not_awaited()
    release.assert_awaited_once()
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        assert generation is not None
        assert generation.provider == ("neironych" if uncertain else "nexus")
        assert generation.status == ("submitting" if uncertain else "retry")
        assert generation.parameters["_provider_route_index"] == (0 if uncertain else 1)
        assert bool(generation.parameters.get("_submission_uncertain")) is uncertain
