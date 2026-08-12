from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieClient, KieTask
from app.services.generation_reliability import GenerationOutboxService
from app.services.model_catalog import ModelCatalog
from app.services.wallet import WalletService


class GenerationProviderService:
    @classmethod
    async def submit_kie(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation

        model_id = str((generation.parameters or {}).get("_model_id") or "")
        spec = ModelCatalog.get(model_id)
        generation.status = "submitting"
        generation.error = None
        await session.commit()

        callback_url = settings.webhook_url("webhooks/kie")
        if callback_url:
            callback_url = f"{callback_url}?generation_id={generation.id}"

        client = KieClient(settings.kie_api_key, settings.kie_base_url)
        try:
            task_id = await client.create_task(
                model=spec.kie_model,
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
        if generation.status == "failed":
            # A concurrent recovery path already made this terminal.
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

        # If the worker died after Kie accepted createTask but before taskId was
        # persisted, the callback still carries our local generation_id in its URL.
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
            task = await client.get_task(task_id)
        finally:
            await client.aclose()
        await cls.apply_kie_task(session, generation, task)
        return generation

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
            generation.parameters = {
                **generation.parameters,
                "_result_urls": task.result_urls,
            }
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
