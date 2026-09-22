from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieTask
from app.providers.nexus import NANO_BANANA_MODELS, NexusClient, NexusProviderError
from app.services.feed_static import FeedStaticStorage
from app.services.generation_provider import GenerationProviderService
from app.services.reference_static import ReferenceStaticStorage


class NexusGenerationContractError(ValueError):
    pass


logger = logging.getLogger(__name__)


class NexusGenerationProviderService:
    MODEL_IDS = NANO_BANANA_MODELS

    @classmethod
    def handles(cls, generation: Generation) -> bool:
        return str((generation.parameters or {}).get("_model_id") or "") in cls.MODEL_IDS

    @staticmethod
    def provider_name(generation: Generation) -> str:
        return "nexus" if NexusGenerationProviderService.handles(generation) else "kie"

    @staticmethod
    def _nexus_reference_url(raw: str) -> str:
        """Return a deterministic URL Nexus can fetch without KIE transport.

        Product-owned relative URLs are expanded against PUBLIC_BASE_URL. Absolute
        HTTP(S) references are kept byte-for-byte so retries with the same Nexus
        Idempotency-Key also keep the exact same request body.
        """

        value = str(raw or "").strip()
        if not value:
            raise NexusGenerationContractError("Nexus reference URL must not be empty")

        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"} and parsed.netloc:
            return value

        if not (
            ReferenceStaticStorage.is_local_url(value)
            or FeedStaticStorage.is_local_url(value)
        ):
            raise NexusGenerationContractError(
                "Nexus reference must be an absolute URL or product-owned media URL"
            )

        base = urlsplit(settings.public_base_url.strip())
        if base.scheme != "https" or not base.netloc:
            raise NexusGenerationContractError(
                "PUBLIC_BASE_URL must be HTTPS to send stored references to Nexus"
            )
        path = parsed.path or value.split("?", 1)[0]
        return urlunsplit((base.scheme, base.netloc, path, "", ""))

    @classmethod
    def _normalize_input(cls, model_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if model_id not in NANO_BANANA_MODELS:
            raise NexusGenerationContractError(f"Unsupported Nexus model: {model_id}")

        prompt = str(input_data.get("prompt") or "").strip()
        if not prompt:
            raise NexusGenerationContractError("Prompt must not be empty")

        raw_refs = input_data.get("image_input")
        if raw_refs in (None, ""):
            raw_refs = input_data.get("image_urls")
        if raw_refs in (None, ""):
            raw_values: list[str] = []
        elif isinstance(raw_refs, (list, tuple)):
            raw_values = [str(item).strip() for item in raw_refs if str(item).strip()]
        else:
            raw_values = [str(raw_refs).strip()]
        refs = list(dict.fromkeys(cls._nexus_reference_url(item) for item in raw_values))

        return {
            "prompt": prompt,
            "aspect_ratio": str(input_data.get("aspect_ratio") or "1:1"),
            "image_size": str(
                input_data.get("image_size") or input_data.get("resolution") or "2K"
            ).upper(),
            "image_urls": refs,
        }

    @staticmethod
    def _error_disposition(exc: Exception) -> str:
        if isinstance(exc, NexusGenerationContractError):
            return "permanent"
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status == 429:
                return "retryable"
            if 400 <= status < 500 and status not in {408, 425}:
                return "permanent"
            return "uncertain"
        if isinstance(exc, (httpx.TransportError, json.JSONDecodeError)):
            return "uncertain"
        if isinstance(exc, NexusProviderError):
            message = str(exc).lower()
            if (
                "not configured" in message
                or "unsupported" in message
                or "must not be empty" in message
                or "at most" in message
            ):
                return "permanent"
            return "uncertain"
        return "permanent"

    @classmethod
    async def _record_submission_error(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        exc: Exception,
    ) -> None:
        disposition = cls._error_disposition(exc)
        if disposition == "permanent":
            await GenerationProviderService.fail_and_refund(session, generation_id, str(exc))
            return

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None or generation.status in {"succeeded", "failed"}:
            return

        now = datetime.now(timezone.utc)
        # Nexus caches successful /generate responses by Idempotency-Key for 24h.
        # Requeue uncertain outcomes so the durable worker safely replays the exact
        # same logical request and recovers the original task_id instead of waiting
        # for a callback that image tasks do not require.
        generation.status = "retry"
        generation.error = f"Nexus submission {disposition}: {exc}"[:4000]
        generation.updated_at = now
        generation.provider = "nexus"
        parameters = dict(generation.parameters or {})
        if disposition == "uncertain":
            parameters["_submission_uncertain"] = True
            parameters["_submission_uncertain_at"] = now.isoformat()
        else:
            parameters.pop("_submission_uncertain", None)
            parameters.pop("_submission_uncertain_at", None)
        generation.parameters = parameters
        await session.commit()

    @classmethod
    async def submit(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation
        if not cls.handles(generation):
            raise NexusGenerationContractError("Generation is not routed to Nexus")

        model_id = str((generation.parameters or {}).get("_model_id") or "")
        generation.provider = "nexus"
        generation.status = "submitting"
        generation.error = None
        await session.commit()

        try:
            input_data = GenerationProviderService._input_for(generation)
            normalized = cls._normalize_input(model_id, input_data)

            log_input = {k: v for k, v in normalized.items()}
            if "prompt" in log_input:
                log_input["prompt"] = (log_input["prompt"] or "")[:200]
            if "image_urls" in log_input:
                log_input["image_urls"] = f"count={len(log_input['image_urls'])}"
            logger.info(
                "nexus_submit submitting gen=%s model=%s normalized=%s",
                generation_id, model_id, log_input,
            )

            client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
            try:
                task_id = await client.create_nano_banana(
                    model_name=model_id,
                    prompt=normalized["prompt"],
                    aspect_ratio=normalized["aspect_ratio"],
                    image_size=normalized["image_size"],
                    image_urls=normalized["image_urls"],
                    idempotency_key=f"generation:{generation.id}",
                )
            finally:
                await client.aclose()
        except Exception as exc:
            await cls._record_submission_error(session, generation.id, exc)
            raise

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation disappeared after Nexus submission")
        if generation.status in {"succeeded", "failed"}:
            return generation
        if generation.external_id and generation.external_id != task_id:
            return generation

        now = datetime.now(timezone.utc)
        generation.external_id = task_id
        generation.provider = "nexus"
        generation.status = "generating"
        generation.error = None
        generation.updated_at = now
        GenerationProviderService._mark_provider_task_bound(generation, now=now)
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
            candidate = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
            if (
                candidate is not None
                and candidate.external_id == task_id
                and candidate.provider == "nexus"
            ):
                generation = candidate
        if generation is None or generation.status in {"succeeded", "failed"}:
            return generation

        client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
        try:
            task = await client.get_task(task_id)
        finally:
            await client.aclose()

        if task.status == "completed" and not task.image_urls:
            generation.status = "generating"
            generation.error = "Nexus reported completed without result URLs; awaiting reconciliation"
            generation.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return generation

        state = (
            "success"
            if task.status == "completed"
            else "fail"
            if task.status == "failed"
            else task.status
        )
        logger.info(
            "nexus_sync_task gen=%s task=%s nexus_status=%s state=%s urls=%s",
            generation_id, task_id, task.status, state,
            f"count={len(task.image_urls)}" if task.image_urls else "none",
        )
        provider_task = KieTask(
            task_id=task.task_id,
            state=state,
            result_urls=task.image_urls,
            fail_code="nexus_failed" if task.status == "failed" else "",
            fail_message=task.error or ("Nexus generation failed" if task.status == "failed" else ""),
            raw=task.raw,
        )
        await GenerationProviderService.apply_kie_task(session, generation, provider_task)
        return generation
