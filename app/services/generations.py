import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.services.abuse_protection import AbuseProtectionService, GenerationAdmissionService
from app.services.credits import InternalCreditService
from app.services.generation_reliability import GenerationOutboxService
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)


class GenerationService:
    # Kept for compatibility with older deployments/metrics. The worker no longer
    # treats this Redis list as the durable source of work.
    QUEUE_KEY = "queue:generations"
    WAKE_KEY = "wake:generations"

    @classmethod
    async def _resolve_billing_seconds(
        cls,
        session: AsyncSession,
        *,
        model_id: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
    ) -> int | None:
        if billing_seconds is not None:
            return billing_seconds
        if model_id != "grok-video-upscale":
            return None

        task_id = str(parameters.get("task_id") or "")
        if not task_id:
            return None
        source = await session.scalar(select(Generation).where(Generation.external_id == task_id))
        if source is None:
            return None
        source_seconds = (source.parameters or {}).get("_billing_seconds")
        try:
            return int(source_seconds) if source_seconds is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _apply_input_url(spec: ModelSpec, parameters: dict[str, Any], input_url: str | None) -> None:
        if not input_url:
            return
        if any(
            parameters.get(key)
            for key in (
                "image_url",
                "image_urls",
                "image_input",
                "input_urls",
                "first_frame_url",
                "first_frame",
            )
        ):
            return
        fields = set(spec.known_fields)
        if "first_frame_url" in fields:
            parameters["first_frame_url"] = input_url
        elif "image_urls" in fields:
            parameters["image_urls"] = [input_url]
        elif "input_urls" in fields:
            parameters["input_urls"] = [input_url]
        elif "image_input" in fields:
            parameters["image_input"] = [input_url]
        elif "image_url" in fields:
            parameters["image_url"] = input_url
        elif "first_frame" in fields:
            parameters["first_frame"] = input_url

    @classmethod
    async def prepare_request(
        cls,
        session: AsyncSession,
        *,
        model_id: str,
        prompt: str,
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
    ) -> tuple[ModelSpec, dict[str, Any], Decimal, int | None, Decimal]:
        spec = ModelCatalog.get(model_id)
        merged = dict(parameters or {})
        if prompt and not merged.get("prompt"):
            merged["prompt"] = prompt
        cls._apply_input_url(spec, merged, input_url)
        resolved_seconds = await cls._resolve_billing_seconds(
            session,
            model_id=model_id,
            parameters=merged,
            billing_seconds=billing_seconds,
        )
        spec, clean, cost_rox, seconds, unit_price = ModelCatalog.prepare(
            model_id,
            merged,
            billing_seconds=resolved_seconds,
        )

        # Built-in catalog prices were authored when one internal credit represented
        # 10 RUB. ROXY is 1 RUB, so redenominate only built-in defaults. Explicit
        # GENERATION_PRICING_JSON overrides are already operator-owned public ROX.
        if model_id not in ModelCatalog._pricing_overrides():
            unit_price = InternalCreditService.legacy_credits_to_rox(unit_price)
            multiplier = Decimal(seconds) if seconds is not None else Decimal("1")
            cost_rox = (unit_price * multiplier).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return spec, clean, cost_rox, seconds, unit_price

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str = "",
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
        source_feed_gen_id: uuid.UUID | None = None,
        parent_generation_id: uuid.UUID | None = None,
        action_type: str | None = None,
    ) -> Generation:
        spec, clean, cost_rox, seconds, unit_price = await cls.prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
        )

        # Reject abusive/over-budget work before any wallet debit/provider side effect.
        # The DB admission lock remains held until the same transaction commits.
        await AbuseProtectionService.generation_rate(redis, user_id)
        await GenerationAdmissionService.enforce(
            session,
            user_id=user_id,
            next_cost=cost_rox,
        )

        generation = Generation(
            user_id=user_id,
            kind=spec.operation,
            prompt=str(clean.get("prompt") or prompt or ""),
            input_url=input_url,
            cost_rox=cost_rox,
            provider="kie",
            parameters={
                **clean,
                "_model_id": spec.id,
                "_kie_model": spec.kie_model,
                "_billing_mode": spec.price_mode,
                "_billing_seconds": seconds,
                "_unit_price_rox": str(unit_price),
            },
            status="queued",
            source_feed_gen_id=source_feed_gen_id,
            parent_generation_id=parent_generation_id,
            action_type=action_type,
            publication_scope="private",
            is_public_feed=False,
            is_profile_visible=False,
            feed_prompt_visible=False if source_feed_gen_id else False,
            feed_references_visible=False if source_feed_gen_id else False,
        )
        session.add(generation)
        await session.flush()

        GenerationOutboxService.add(session, generation.id)
        await WalletService.debit(
            session,
            user_id=user_id,
            amount=cost_rox,
            kind="generation",
            reference_type="generation",
            reference_id=str(generation.id),
            idempotency_key=f"generation:{generation.id}:charge",
        )
        await session.commit()

        try:
            await redis.rpush(cls.WAKE_KEY, str(generation.id))
        except RedisError:
            logger.warning("Redis wake-up failed for generation %s; outbox will recover it", generation.id)
        return generation
