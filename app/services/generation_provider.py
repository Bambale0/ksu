from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieClient, KieTask
from app.services.generation_reliability import GenerationOutboxService
from app.services.media_assets import MediaAssetService
from app.services.model_catalog import ModelCatalog
from app.services.music_media import MusicMediaAssetService
from app.services.wallet import WalletService


class GenerationProviderService:
    @staticmethod
    def _provider_api(generation: Generation) -> str:
        return str((generation.parameters or {}).get("_provider_api") or "jobs")

    @classmethod
    async def submit_kie(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation

        provider_api = cls._provider_api(generation)
        if provider_api == "suno_music":
            kie_model = str(
                (generation.parameters or {}).get("_kie_model")
                or settings.music_generation_model
            )
        else:
            model_id = str((generation.parameters or {}).get("_model_id") or "")
            kie_model = ModelCatalog.get(model_id).kie_model

        generation.status = "submitting"
        generation.error = None
        await session.commit()

        callback_url = settings.webhook_url("webhooks/kie")
        if callback_url:
            callback_url = f"{callback_url}?generation_id={generation.id}"

        client = KieClient(settings.kie_api_key, settings.kie_base_url)
        try:
            if provider_api == "suno_music":
                task_id = await client.create_music_task(
                    model=kie_model,
                    input_data=cls._input_for(generation),
                    callback_url=callback_url,
                )
            else:
                task_id = await client.create_task(
                    model=kie_model,
                    input_data=cls._input_for(generation),
                    callback_url=callback_url,
                )
        except Exception as exc:
            await cls.fail_and_refund(session, generation.id, str(exc))
            raise
        finally:
            await client.aclose()

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation disappeared after provider submission")
        if generation.status in {"succeeded", "failed"}:
            return generation
        if generation.external_id and generation.external_id != task_id:
            return generation
        generation.external_id = task_id
        generation.provider = "kie"
        generation.status = "generating"
        generation.error = None
        generation.updated_at = datetime.now(timezone.utc)
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
        generation = await session.scalar(
            select(Generation).where(Generation.external_id == task_id).with_for_update()
        )

        if generation is None and generation_id is not None:
            candidate = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
            if (
                candidate is not None
                and candidate.external_id is None
                and candidate.status in {"queued", "retry", "submitting", "generating"}
            ):
                candidate.external_id = task_id
                candidate.provider = "kie"
                candidate.status = "generating"
                candidate.error = None
                candidate.updated_at = datetime.now(timezone.utc)
                await session.commit()
                generation = candidate

        if generation is None:
            return None

        client = KieClient(settings.kie_api_key, settings.kie_base_url)
        try:
            if cls._provider_api(generation) == "suno_music":
                task = await client.get_music_task(task_id)
            else:
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
        if (
            generation.action_type != "remix"
            or generation.source_feed_gen_id is None
            or settings.prompt_repeat_bonus_rox <= Decimal("0")
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
        if task.state == "success":
            generation.status = "succeeded"
            generation.error = None
            generation.updated_at = datetime.now(timezone.utc)
            if task.result_urls:
                generation.result_url = task.result_urls[0]
            parameters: dict[str, Any] = {
                **generation.parameters,
                "_result_urls": task.result_urls,
            }
            if task.tracks is not None:
                parameters["_music_tracks"] = task.tracks
            generation.parameters = parameters
            # Prompt-author rewards settle only after a successful paid repeat.
            # This prevents failed/refunded provider attempts from minting bonus ROX.
            await cls._award_prompt_repeat_bonus(session, generation)
            # Generation terminal state, author reward, and durable media ingest rows
            # commit together so retries cannot duplicate any of them.
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
        generation.status = "failed"
        generation.error = error[:4000]
        generation.updated_at = datetime.now(timezone.utc)
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
        data = {
            key: value
            for key, value in dict(generation.parameters or {}).items()
            if not key.startswith("_")
        }
        if generation.prompt and not data.get("prompt"):
            data["prompt"] = generation.prompt
        if generation.input_url and not any(
            key in data
            for key in (
                "image_url",
                "image_urls",
                "image_input",
                "input_urls",
                "first_frame_url",
            )
        ):
            data["image_url"] = generation.input_url
        return data