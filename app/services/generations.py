import json
import uuid
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.services.wallet import WalletService


class GenerationService:
    QUEUE_KEY = "queue:generations"

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

        if model_id == "grok-video-extend":
            extend_times = parameters.get("extend_times")
            if extend_times not in (None, "", 0, "0"):
                try:
                    return int(extend_times)
                except (TypeError, ValueError):
                    pass

        if model_id not in {"grok-video-upscale", "grok-video-extend"}:
            return None

        task_id = str(parameters.get("task_id") or "")
        if not task_id:
            return None
        source = await session.scalar(
            select(Generation).where(Generation.external_id == task_id)
        )
        if source is None:
            return None
        source_seconds = (source.parameters or {}).get("_billing_seconds")
        try:
            return int(source_seconds) if source_seconds is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    async def prepare_request(
        cls,
        session: AsyncSession,
        *,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
    ) -> tuple[ModelSpec, dict[str, Any], Decimal, int | None, Decimal]:
        merged = dict(parameters or {})
        if prompt and not merged.get("prompt"):
            merged["prompt"] = prompt
        resolved_seconds = await cls._resolve_billing_seconds(
            session,
            model_id=model_id,
            parameters=merged,
            billing_seconds=billing_seconds,
        )
        return ModelCatalog.prepare(
            model_id,
            merged,
            billing_seconds=resolved_seconds,
        )

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
    ) -> Generation:
        spec, clean, cost_rox, seconds, unit_price = await cls.prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            parameters=parameters,
            billing_seconds=billing_seconds,
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
        )
        session.add(generation)
        await session.flush()

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

        payload = json.dumps({"generation_id": str(generation.id)}, separators=(",", ":"))
        await redis.rpush(cls.QUEUE_KEY, payload)
        return generation
