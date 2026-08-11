from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieClient, KieTask
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

        generation.status = "submitting"
        generation.provider = "kie"
        await session.commit()

        client = KieClient(settings.kie_api_key, settings.kie_base_url)
        try:
            model = settings.kie_model_for(generation.kind)
            task_id = await client.create_task(
                model=model,
                input_data=cls._input_for(generation),
                callback_url=settings.webhook_url("webhooks/kie"),
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
        generation.external_id = task_id
        generation.provider = "kie"
        generation.status = "generating"
        await session.commit()
        return generation

    @classmethod
    async def sync_kie_task(
        cls,
        session: AsyncSession,
        *,
        task_id: str,
    ) -> Generation | None:
        generation = await session.scalar(
            select(Generation).where(Generation.external_id == task_id).with_for_update()
        )
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
            if task.result_urls:
                generation.result_url = task.result_urls[0]
            generation.parameters = {
                **generation.parameters,
                "_result_urls": task.result_urls,
            }
            await session.commit()
            return

        if task.state == "fail":
            message = task.fail_message or task.fail_code or "Kie generation failed"
            await cls.fail_and_refund(session, generation.id, message)
            return

        generation.status = "generating"
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

    @staticmethod
    def _input_for(generation: Generation) -> dict[str, Any]:
        data = dict(generation.parameters or {})
        data.pop("_result_urls", None)
        data.setdefault("prompt", generation.prompt)
        if generation.input_url and not any(
            key in data for key in ("image_url", "image_urls", "input_urls")
        ):
            data["image_url"] = generation.input_url
        return data
