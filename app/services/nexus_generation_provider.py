from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.nexus import NexusClient, NexusProviderError
from app.services.generation_provider_routing import NEXUS_GENERATION_MODELS
from app.services.generation_reliability import GenerationOutboxService
from app.services.media_assets import MediaAssetService
from app.services.provider_media_transport import ProviderMediaTransport
from app.services.reference_resolver import ReferenceResolver
from app.services.wallet import WalletService

_TERMINAL = {"succeeded", "failed"}
_VALID_RATIOS = {
    "auto", "1:1", "16:9", "9:16", "4:3", "3:4",
    "3:2", "2:3", "5:4", "4:5", "21:9",
}
_VALID_SIZES = {"1K", "2K", "4K"}


def _model_id(generation: Generation) -> str:
    return str((generation.parameters or {}).get("_model_id") or "")


def _provider_model(generation: Generation) -> str:
    params = generation.parameters or {}
    return str(params.get("_provider_model") or params.get("_kie_model") or _model_id(generation)).strip()


def _list_urls(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw = value if isinstance(value, (list, tuple)) else [value]
    result: list[str] = []
    for item in raw:
        url = str(item or "").strip()
        if url and url not in result:
            result.append(url)
    return result


def _nexus_input(
    generation: Generation,
    provider_input: dict[str, Any],
) -> tuple[str, str, str, str, list[str]]:
    model = _provider_model(generation)
    if model not in NEXUS_GENERATION_MODELS:
        raise NexusProviderError(f"Unsupported production Nexus model: {model}")

    prompt = str(provider_input.get("prompt") or generation.prompt or "").strip()
    if not prompt:
        raise NexusProviderError("Prompt must not be empty")

    ratio = str(provider_input.get("aspect_ratio") or "1:1").strip()
    if ratio not in _VALID_RATIOS:
        raise NexusProviderError(f"Unsupported Nano Banana aspect ratio: {ratio}")

    size = str(provider_input.get("resolution") or provider_input.get("image_size") or "2K").upper()
    if size not in _VALID_SIZES:
        raise NexusProviderError(f"Unsupported Nano Banana image size: {size}")

    refs: list[str] = []
    for key in ("image_input", "image_urls", "input_urls", "reference_image_urls", "image_url"):
        for url in _list_urls(provider_input.get(key)):
            if url not in refs:
                refs.append(url)
    if len(refs) > 4:
        raise NexusProviderError("Nano Banana accepts at most 4 reference images")
    return model, prompt, ratio, size, refs


class NexusGenerationProviderService:
    @staticmethod
    async def _mark_retry(session: AsyncSession, generation_id: uuid.UUID, error: str) -> None:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None or generation.status in _TERMINAL:
            return
        generation.status = "retry"
        generation.error = error[:4000]
        generation.updated_at = datetime.now(timezone.utc)
        await session.commit()

    @staticmethod
    async def _fail_and_refund(session: AsyncSession, generation_id: uuid.UUID, error: str) -> None:
        from app.services.generation_provider import GenerationProviderService

        await GenerationProviderService.fail_and_refund(session, generation_id, error)

    @classmethod
    async def submit(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation
        if _model_id(generation) not in NEXUS_GENERATION_MODELS:
            raise NexusProviderError("Generation is not routed to Nexus")

        generation.status = "submitting"
        generation.error = None
        await session.commit()

        try:
            provider_input = dict(ReferenceResolver.generation_context(generation).provider_input)
            provider_input = await ProviderMediaTransport.prepare(provider_input)
            model, prompt, ratio, size, refs = _nexus_input(generation, provider_input)
            client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
            try:
                task_id = await client.create_nano_banana(
                    model_name=model,
                    prompt=prompt,
                    aspect_ratio=ratio,
                    image_size=size,
                    image_urls=refs,
                    idempotency_key=f"generation:{generation.id}",
                )
            finally:
                await client.aclose()
        except Exception as exc:
            permanent = isinstance(exc, NexusProviderError)
            if isinstance(exc, httpx.HTTPStatusError):
                code = exc.response.status_code
                permanent = 400 <= code < 500 and code != 429
            if permanent:
                await cls._fail_and_refund(session, generation_id, str(exc))
            else:
                await cls._mark_retry(session, generation_id, f"Nexus submission retryable: {exc}")
            raise

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation disappeared after Nexus submission")
        if generation.status in _TERMINAL:
            return generation

        now = datetime.now(timezone.utc)
        generation.provider = "nexus"
        generation.external_id = task_id
        generation.status = "generating"
        generation.error = None
        generation.updated_at = now
        params = dict(generation.parameters or {})
        params["_provider_submitted_at"] = now.isoformat()
        params.pop("_submission_uncertain", None)
        params.pop("_submission_uncertain_at", None)
        generation.parameters = params
        await session.commit()
        return generation

    @classmethod
    async def sync_task(
        cls,
        session: AsyncSession,
        *,
        task_id: str,
        generation_id: uuid.UUID | None = None,
    ) -> Generation | None:
        generation = await session.scalar(
            select(Generation)
            .where(Generation.provider == "nexus", Generation.external_id == task_id)
            .with_for_update()
        )
        if generation is None and generation_id is not None:
            generation = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
        if generation is None or generation.status in _TERMINAL:
            return generation

        client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
        try:
            task = await client.get_task(task_id)
        finally:
            await client.aclose()

        if task.status == "completed":
            if not task.image_urls:
                generation.status = "generating"
                generation.error = "Nexus completed without image URLs; awaiting reconciliation"
                generation.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return generation

            generation.status = "succeeded"
            generation.error = None
            generation.result_url = task.image_urls[0]
            generation.updated_at = datetime.now(timezone.utc)
            generation.parameters = {**(generation.parameters or {}), "_result_urls": task.image_urls}

            if (
                generation.action_type == "remix"
                and generation.source_feed_gen_id is not None
                and settings.prompt_repeat_bonus_rox > Decimal("0")
                and Decimal(generation.cost_rox) > 0
                and not bool((generation.parameters or {}).get("_admin_free"))
            ):
                source = await session.get(Generation, generation.source_feed_gen_id)
                if source is not None and source.user_id != generation.user_id:
                    await WalletService.credit(
                        session,
                        user_id=source.user_id,
                        amount=settings.prompt_repeat_bonus_rox,
                        kind="prompt_repeat_bonus",
                        reference_type="generation",
                        reference_id=str(generation.id),
                        idempotency_key=f"prompt-repeat:{generation.id}",
                    )

            await MediaAssetService.enqueue_results(session, generation, task.image_urls)
            await session.commit()
            await GenerationOutboxService.mark_generation_terminal(session, generation.id, failed=False)
            return generation

        if task.status == "failed":
            await cls._fail_and_refund(
                session,
                generation.id,
                task.error or f"Nexus task {task_id} failed",
            )
            return await session.get(Generation, generation.id)

        generation.status = "generating"
        generation.error = None
        generation.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return generation
