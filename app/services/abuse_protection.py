from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation, User
from app.providers.kie import KieProviderError

logger = logging.getLogger(__name__)


class ResourcePolicyError(RuntimeError):
    code = "resource_policy"

    def __init__(self, message: str, *, retry_after: int = 1) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


class ResourceLimitExceeded(ResourcePolicyError):
    code = "resource_limit_exceeded"


class ProtectionBackendUnavailable(ResourcePolicyError):
    code = "protection_backend_unavailable"


class ProviderCircuitOpen(ResourcePolicyError):
    code = "provider_circuit_open"


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    used: int
    limit: int
    retry_after: int


class AbuseProtectionService:
    RATE_LUA = """
local current = redis.call('INCRBY', KEYS[1], ARGV[1])
if current == tonumber(ARGV[1]) then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

    CIRCUIT_FAILURE_LUA = """
local failures = redis.call('INCR', KEYS[1])
if failures == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if failures >= tonumber(ARGV[2]) then
  redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
end
local ttl = redis.call('TTL', KEYS[2])
return {failures, ttl}
"""

    @staticmethod
    def _enabled() -> bool:
        return settings.abuse_protection_enabled

    @classmethod
    async def consume(
        cls,
        redis: Redis,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        amount: int = 1,
        message: str = "Too many requests",
    ) -> RateLimitResult:
        if not cls._enabled() or limit <= 0:
            return RateLimitResult(used=0, limit=limit, retry_after=0)
        if amount <= 0:
            return RateLimitResult(used=0, limit=limit, retry_after=0)
        try:
            result = await redis.eval(
                cls.RATE_LUA,
                1,
                key,
                int(amount),
                max(1, int(window_seconds)),
            )
        except (RedisError, AttributeError, TypeError) as exc:
            if settings.abuse_fail_closed:
                raise ProtectionBackendUnavailable(
                    "Resource protection store is unavailable",
                    retry_after=5,
                ) from exc
            logger.warning("Abuse protection fail-open for %s: %s", key, exc)
            return RateLimitResult(used=0, limit=limit, retry_after=0)

        used = int(result[0])
        ttl = max(1, int(result[1] if len(result) > 1 else window_seconds))
        if used > limit:
            raise ResourceLimitExceeded(message, retry_after=ttl)
        return RateLimitResult(used=used, limit=limit, retry_after=ttl)

    @classmethod
    async def generation_rate(cls, redis: Redis, user_id: uuid.UUID) -> None:
        await cls.consume(
            redis,
            key=f"abuse:generation:user:{user_id}",
            limit=settings.generation_rate_limit_per_minute,
            window_seconds=60,
            message="Generation rate limit exceeded",
        )

    @classmethod
    async def upload_rate_and_bytes(
        cls,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        size_bytes: int,
    ) -> None:
        await cls.consume(
            redis,
            key=f"abuse:upload:req:{user_id}",
            limit=settings.upload_rate_limit_per_minute,
            window_seconds=60,
            message="Upload rate limit exceeded",
        )
        if settings.upload_daily_bytes_limit > 0:
            day = datetime.now(timezone.utc).date().isoformat()
            await cls.consume(
                redis,
                key=f"abuse:upload:bytes:{user_id}:{day}",
                limit=settings.upload_daily_bytes_limit,
                window_seconds=86_400,
                amount=max(0, size_bytes),
                message="Daily upload quota exceeded",
            )

    @classmethod
    async def payment_rate(cls, redis: Redis, user_id: uuid.UUID) -> None:
        await cls.consume(
            redis,
            key=f"abuse:payment:user:{user_id}",
            limit=settings.payment_create_rate_limit_per_minute,
            window_seconds=60,
            message="Payment creation rate limit exceeded",
        )

    @classmethod
    async def provider_submission_gate(cls, redis: Redis, provider: str = "kie") -> None:
        if not cls._enabled():
            return
        open_key = f"abuse:circuit:{provider}:open"
        try:
            ttl = await redis.ttl(open_key)
            if ttl and int(ttl) > 0:
                raise ProviderCircuitOpen(
                    f"{provider} provider circuit is temporarily open",
                    retry_after=int(ttl),
                )
        except ProviderCircuitOpen:
            raise
        except (RedisError, AttributeError, TypeError) as exc:
            if settings.abuse_fail_closed:
                raise ProtectionBackendUnavailable(
                    "Provider protection store is unavailable",
                    retry_after=5,
                ) from exc
            logger.warning("Provider circuit check failed open for %s: %s", provider, exc)

        await cls.consume(
            redis,
            key=f"abuse:provider-submit:{provider}",
            limit=settings.kie_submit_rate_limit_per_minute,
            window_seconds=60,
            message=f"{provider} submission rate limit reached",
        )

    @classmethod
    async def record_provider_failure(cls, redis: Redis, provider: str = "kie") -> None:
        if not cls._enabled() or settings.kie_circuit_failure_threshold <= 0:
            return
        try:
            await redis.eval(
                cls.CIRCUIT_FAILURE_LUA,
                2,
                f"abuse:circuit:{provider}:failures",
                f"abuse:circuit:{provider}:open",
                settings.kie_circuit_failure_window_seconds,
                settings.kie_circuit_failure_threshold,
                settings.kie_circuit_open_seconds,
            )
        except (RedisError, AttributeError, TypeError):
            logger.exception("Could not record %s provider failure", provider)

    @classmethod
    async def record_provider_success(cls, redis: Redis, provider: str = "kie") -> None:
        if not cls._enabled():
            return
        try:
            await redis.delete(f"abuse:circuit:{provider}:failures")
        except (RedisError, AttributeError, TypeError):
            logger.exception("Could not reset %s provider failure counter", provider)

    @staticmethod
    def availability_failure(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return isinstance(exc, (httpx.RequestError, KieProviderError))


class GenerationAdmissionService:
    ACTIVE_STATUSES = ("queued", "retry", "submitting", "generating")

    @classmethod
    async def enforce(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        next_cost: Decimal,
    ) -> None:
        if not settings.abuse_protection_enabled:
            return

        # Serialize admission decisions per user inside the same transaction that
        # later debits the wallet and creates the generation/outbox row.
        user = await session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise LookupError("User not found")

        if settings.generation_max_active_per_user > 0:
            active = int(
                (
                    await session.scalar(
                        select(func.count()).select_from(Generation).where(
                            Generation.user_id == user_id,
                            Generation.status.in_(cls.ACTIVE_STATUSES),
                        )
                    )
                )
                or 0
            )
            if active >= settings.generation_max_active_per_user:
                raise ResourceLimitExceeded(
                    "Too many active generations",
                    retry_after=max(5, settings.generation_reconcile_stale_seconds),
                )

        daily_limit = Decimal(settings.generation_daily_spend_limit_credits)
        if daily_limit > 0:
            now = datetime.now(timezone.utc)
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            spent = Decimal(
                (
                    await session.scalar(
                        select(func.coalesce(func.sum(Generation.cost_rox), 0)).where(
                            Generation.user_id == user_id,
                            Generation.created_at >= start,
                        )
                    )
                )
                or 0
            )
            if spent + next_cost > daily_limit:
                seconds_until_midnight = int(
                    (
                        datetime.combine(
                            now.date(),
                            time.max,
                            tzinfo=timezone.utc,
                        )
                        - now
                    ).total_seconds()
                ) + 1
                raise ResourceLimitExceeded(
                    "Daily generation spend limit exceeded",
                    retry_after=max(1, seconds_until_midnight),
                )
