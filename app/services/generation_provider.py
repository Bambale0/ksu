from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieClient, KieProviderError, KieTask
from app.providers.kie_veo import KieVeoClient
from app.services.generation_reliability import GenerationOutboxService
from app.services.kie_image_contracts import KieImageContractError
from app.services.kie_video_contracts import KieVideoContractError
from app.services.media_assets import MediaAssetService
from app.services.model_catalog import ModelCatalog
from app.services.music_media import MusicMediaAssetService
from app.services.provider_media_transport import (
    ProviderMediaTransport,
    ProviderMediaTransportError,
    ProviderMediaTransportPermanentError,
)
from app.services.reference_resolver import ReferenceResolver
from app.services.wallet import WalletService

SubmissionDisposition = Literal["permanent", "retryable", "uncertain"]
_TERMINAL_STATUSES = {"succeeded", "failed"}
_UNCERTAIN_CLIENT_STATUSES = {408, 425}
class GenerationProviderService:
    @staticmethod
    def _provider_api(generation: Generation) -> str:
        return str((generation.parameters or {}).get("_provider_api") or "jobs")

    @staticmethod
    def _model_id(generation: Generation) -> str:
        return str((generation.parameters or {}).get("_model_id") or "")

    @staticmethod
    def _provider_model_snapshot(generation: Generation) -> str:
        """Return the provider identity frozen when the generation was created."""

        params = generation.parameters or {}
        stored = str(params.get("_provider_model") or params.get("_kie_model") or "").strip()
        if stored:
            return stored
        if GenerationProviderService._provider_api(generation) == "suno_music":
            return str(settings.music_generation_model)
        return ModelCatalog.get(GenerationProviderService._model_id(generation)).kie_model

    @staticmethod
    def _submission_error_disposition(exc: Exception) -> SubmissionDisposition:
        """Classify create-task failures by whether a provider task may exist."""

        if isinstance(exc, (KieImageContractError, KieVideoContractError)):
            return "permanent"
        if isinstance(exc, ProviderMediaTransportPermanentError):
            return "permanent"
        if isinstance(exc, ProviderMediaTransportError):
            # Media transport happens before create-task, so retrying cannot
            # duplicate a paid generation task upstream.
            return "retryable"

        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code == 429:
                return "retryable"
            if 400 <= status_code < 500 and status_code not in _UNCERTAIN_CLIENT_STATUSES:
                return "permanent"
            return "uncertain"

        if isinstance(exc, httpx.TransportError):
            return "uncertain"
        if isinstance(exc, json.JSONDecodeError):
            return "uncertain"

        if isinstance(exc, KieProviderError):
            message = str(exc).lower()
            if "not configured" in message or " rejected:" in message:
                return "permanent"
            return "uncertain"

        return "permanent"

    @classmethod
    async def _record_submission_error(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        exc: Exception,
    ) -> SubmissionDisposition:
        disposition = cls._submission_error_disposition(exc)
        if disposition == "permanent":
            await cls.fail_and_refund(session, generation_id, str(exc))
            return disposition

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None or generation.status in _TERMINAL_STATUSES:
            return disposition

        now = datetime.now(timezone.utc)
        generation.status = "retry" if disposition == "retryable" else "submitting"
        generation.error = f"Kie submission {disposition}: {exc}"[:4000]
        generation.updated_at = now

        parameters = dict(generation.parameters or {})
        if disposition == "uncertain":
            parameters["_submission_uncertain"] = True
            parameters["_submission_uncertain_at"] = now.isoformat()
        else:
            parameters.pop("_submission_uncertain", None)
            parameters.pop("_submission_uncertain_at", None)
        generation.parameters = parameters
        await session.commit()
        return disposition

    @staticmethod
    def _mark_provider_task_bound(generation: Generation, *, now: datetime) -> None:
        parameters = dict(generation.parameters or {})
        parameters["_provider_submitted_at"] = now.isoformat()
        parameters.pop("_submission_uncertain", None)
        parameters.pop("_submission_uncertain_at", None)
        generation.parameters = parameters

    @classmethod
    async def submit_kie(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        """Submit a generation to the exact provider model frozen on creation."""

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation

        provider_api = cls._provider_api(generation)
        model_id = cls._model_id(generation)
        provider_model = cls._provider_model_snapshot(generation)

        generation.status = "submitting"
        generation.error = None
        await session.commit()

        callback_url = settings.webhook_url("webhooks/kie")
        if callback_url:
            params = {"generation_id": str(generation.id)}
            if settings.kie_webhook_hmac_key:
                params["token"] = settings.kie_webhook_hmac_key
            callback_url = f"{callback_url}?{urlencode(params)}"
        input_data = cls._input_for(generation)

        try:
            input_data = await ProviderMediaTransport.prepare(input_data)
            if provider_api == "suno_music":
                client = KieClient(settings.kie_api_key, settings.kie_base_url)
                try:
                    task_id = await client.create_music_task(
                        model=provider_model,
                        input_data=input_data,
                        callback_url=callback_url,
                    )
                finally:
                    await client.aclose()
            elif model_id == "veo-3.1":
                client = KieVeoClient(settings.kie_api_key, settings.kie_base_url)
                try:
                    task_id = await client.create_task(input_data=input_data)
                finally:
                    await client.aclose()
            else:
                client = KieClient(settings.kie_api_key, settings.kie_base_url)
                try:
                    task_id = await client.create_task(
                        model=provider_model,
                        input_data=input_data,
                        callback_url=callback_url,
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
            raise LookupError("Generation disappeared after provider submission")
        if generation.status in _TERMINAL_STATUSES:
            return generation
        if generation.external_id and generation.external_id != task_id:
            return generation

        now = datetime.now(timezone.utc)
        generation.external_id = task_id
        generation.provider = "kie"
        generation.status = "generating"
        generation.error = None
        generation.updated_at = now
        cls._mark_provider_task_bound(generation, now=now)
        await session.commit()
        return generation

    @classmethod
    async def sync_kie_task(
        cls,
        session: AsyncSession,
        *,
        task_id: str,
        generation_id: uuid.UUID | None = None,
    ) -> Generation | None:
        """Synchronize a Kie task using the model's actual status API."""

        generation = await session.scalar(
            select(Generation).where(Generation.external_id == task_id).with_for_update()
        )
        if generation is not None and generation.status in _TERMINAL_STATUSES:
            return generation

        if generation is None and generation_id is not None:
            candidate = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
            if (
                candidate is not None
                and candidate.external_id is None
                and candidate.status in {"queued", "retry", "submitting", "generating"}
            ):
                now = datetime.now(timezone.utc)
                candidate.external_id = task_id
                candidate.provider = "kie"
                candidate.status = "generating"
                candidate.error = None
                candidate.updated_at = now
                cls._mark_provider_task_bound(candidate, now=now)
                await session.commit()
                generation = candidate

        if generation is None or generation.status in _TERMINAL_STATUSES:
            return generation

        model_id = cls._model_id(generation)
        if cls._provider_api(generation) == "suno_music":
            client = KieClient(settings.kie_api_key, settings.kie_base_url)
            try:
                task = await client.get_music_task(task_id)
            finally:
                await client.aclose()
        elif model_id == "veo-3.1":
            client = KieVeoClient(settings.kie_api_key, settings.kie_base_url)
            try:
                task = await client.get_task(task_id)
            finally:
                await client.aclose()
        else:
            client = KieClient(settings.kie_api_key, settings.kie_base_url)
            try:
                task = await client.get_task(task_id)
            finally:
                await client.aclose()
        await cls.apply_kie_task(session, generation, task)
        return generation

    @classmethod
    async def _award_prompt_repeat_bonus(
        cls,
        session: AsyncSession,
        generation: Generation,
    ) -> None:
        params = generation.parameters or {}
        if (
            generation.action_type != "remix"
            or generation.source_feed_gen_id is None
            or settings.prompt_repeat_bonus_rox <= Decimal("0")
            or Decimal(generation.cost_rox) <= 0
            or bool(params.get("_admin_free"))
        ):
            return
        source = await session.get(Generation, generation.source_feed_gen_id)
        if source is None or source.user_id == generation.user_id:
            return
        await WalletService.credit(
            session,
            user_id=source.user_id,
            amount=settings.prompt_repeat_bonus_rox,
            kind="prompt_repeat_bonus",
            reference_type="generation",
            reference_id=str(generation.id),
            idempotency_key=f"prompt-repeat:{generation.id}",
        )

    @classmethod
    async def apply_kie_task(
        cls,
        session: AsyncSession,
        generation: Generation,
        task: KieTask,
    ) -> None:
        if generation.status in _TERMINAL_STATUSES:
            return

        if task.state == "success":
            if not task.result_urls:
                generation.status = "generating"
                generation.error = "Kie reported success without result URLs; awaiting reconciliation"
                generation.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return

            generation.status = "succeeded"
            generation.error = None
            generation.updated_at = datetime.now(timezone.utc)
            generation.result_url = task.result_urls[0]
            parameters: dict[str, Any] = {
                **generation.parameters,
                "_result_urls": task.result_urls,
            }
            if task.tracks is not None:
                parameters["_music_tracks"] = task.tracks
            generation.parameters = parameters
            await cls._award_prompt_repeat_bonus(session, generation)
            if cls._provider_api(generation) == "suno_music":
                await MusicMediaAssetService.enqueue_results(
                    session,
                    generation,
                    task.result_urls,
                )
            else:
                await MediaAssetService.enqueue_results(session, generation, task.result_urls)
            await session.commit()
            await GenerationOutboxService.mark_generation_terminal(
                session,
                generation.id,
                failed=False,
            )
            return

        if task.state == "fail":
            message = task.fail_message or task.fail_code or "Kie generation failed"
            await cls.fail_and_refund(session, generation.id, message)
            return

        generation.status = "generating"
        generation.error = None
        generation.updated_at = datetime.now(timezone.utc)
        await session.commit()

    @classmethod
    async def fail_and_refund(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        error: str,
    ) -> None:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            return
        if generation.status == "succeeded":
            return
        if generation.status == "failed":
            await GenerationOutboxService.mark_generation_terminal(
                session,
                generation.id,
                failed=True,
                error=generation.error or error,
            )
            return

        generation.status = "failed"
        generation.error = error[:4000]
        generation.updated_at = datetime.now(timezone.utc)
        if Decimal(generation.cost_rox) > 0:
            await WalletService.credit(
                session,
                user_id=generation.user_id,
                amount=generation.cost_rox,
                kind="generation_refund",
                reference_type="generation",
                reference_id=str(generation.id),
                idempotency_key=f"generation:{generation.id}:refund",
            )
        await session.commit()
        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=True,
            error=error,
        )

    @staticmethod
    def _input_for(generation: Generation) -> dict[str, Any]:
        return ReferenceResolver.generation_context(generation).provider_input
