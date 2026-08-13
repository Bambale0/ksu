from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.services.generation_reliability import GenerationOutboxService
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.services.references import ReferenceService
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

INPUT_FIELDS = {"image_url", "image_urls", "image_input", "input_urls"}
ACTIVE_STATUSES = {"queued", "retry", "submitting", "generating"}


class BatchGenerationError(ValueError):
    pass


class BatchIdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedBatchItem:
    input_url: str
    spec: ModelSpec
    clean: dict[str, Any]
    cost: Decimal
    billing_seconds: int | None
    unit_price: Decimal


def amount(value: Decimal | int | str) -> str:
    return format(Decimal(value), ".2f")


def request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def resolve_inputs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    input_urls: list[str],
    reference_ids: list[uuid.UUID],
    min_items: int = 2,
    max_items: int = 20,
) -> list[str]:
    urls: list[str] = []
    for raw in input_urls:
        value = str(raw or "").strip()
        if value:
            urls.append(ReferenceService._safe_url(value))
    references = await ReferenceService.resolve_owned(
        session,
        user_id=user_id,
        reference_ids=reference_ids,
    )
    for reference in references:
        if reference.kind != "image":
            raise BatchGenerationError("Batch generation accepts image references only")
        urls.append(reference.source_url)
    urls = list(dict.fromkeys(urls))
    if len(urls) < min_items or len(urls) > max_items:
        raise BatchGenerationError(
            f"Batch must contain {min_items}..{max_items} unique images"
        )
    return urls


async def prepare_items(
    session: AsyncSession,
    *,
    model_id: str,
    prompt: str,
    parameters: dict[str, Any],
    billing_seconds: int | None,
    input_urls: list[str],
) -> list[PreparedBatchItem]:
    spec = ModelCatalog.get(model_id)
    if spec.media_type != "image":
        raise BatchGenerationError("Batch generation currently supports image models only")
    if not (INPUT_FIELDS & set(spec.known_fields)):
        raise BatchGenerationError("Selected model does not accept an image input")
    injected = sorted(key for key in INPUT_FIELDS if parameters.get(key))
    if injected:
        raise BatchGenerationError(
            "Batch input images are server-owned; remove: " + ", ".join(injected)
        )

    prepared: list[PreparedBatchItem] = []
    for input_url in input_urls:
        item_spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
        )
        prepared.append(
            PreparedBatchItem(
                input_url=input_url,
                spec=item_spec,
                clean=clean,
                cost=Decimal(cost),
                billing_seconds=seconds,
                unit_price=Decimal(unit_price),
            )
        )
    return prepared


async def enqueue_generation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    batch_id: uuid.UUID,
    item_id: uuid.UUID,
    ordinal: int,
    prepared: PreparedBatchItem,
    prompt: str,
    parent_generation_id: uuid.UUID | None = None,
    retry_count: int = 0,
) -> Generation:
    generation = Generation(
        user_id=user_id,
        kind=prepared.spec.operation,
        prompt=str(prepared.clean.get("prompt") or prompt or ""),
        input_url=prepared.input_url,
        cost_rox=prepared.cost,
        provider="kie",
        parameters={
            **prepared.clean,
            "_model_id": prepared.spec.id,
            "_kie_model": prepared.spec.kie_model,
            "_billing_mode": prepared.spec.price_mode,
            "_billing_seconds": prepared.billing_seconds,
            "_unit_price_rox": str(prepared.unit_price),
            "_batch_id": str(batch_id),
            "_batch_item_id": str(item_id),
            "_batch_ordinal": ordinal,
            "_batch_retry": retry_count,
        },
        status="queued",
        parent_generation_id=parent_generation_id,
        action_type="batch_retry" if retry_count else "batch",
        publication_scope="private",
        is_public_feed=False,
        is_profile_visible=False,
        feed_prompt_visible=False,
        feed_references_visible=False,
    )
    session.add(generation)
    await session.flush()
    GenerationOutboxService.add(session, generation.id)
    await WalletService.debit(
        session,
        user_id=user_id,
        amount=prepared.cost,
        kind="generation",
        reference_type="generation",
        reference_id=str(generation.id),
        idempotency_key=f"generation:{generation.id}:charge",
    )
    return generation


async def wake_generations(redis: Redis, generation_ids: list[uuid.UUID]) -> None:
    if not generation_ids:
        return
    try:
        await redis.rpush(
            GenerationService.WAKE_KEY,
            *[str(generation_id) for generation_id in generation_ids],
        )
    except RedisError:
        logger.warning(
            "Redis batch wake-up failed; durable outbox will recover %s items",
            len(generation_ids),
        )
