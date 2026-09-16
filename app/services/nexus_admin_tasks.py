from __future__ import annotations

import base64
import logging
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.nexus_models import NexusAdminTask
from app.db.session import SessionFactory
from app.providers.nexus import NexusClient, NexusProviderError

logger = logging.getLogger(__name__)

MAX_REFERENCE_FILE_BYTES = 8 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 24 * 1024 * 1024
_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})


def utcnow() -> datetime:
    return datetime.now(UTC)


def _retry_delay(attempts: int) -> int:
    exponent = min(max(attempts - 1, 0), 5)
    delay = max(settings.nexus_test_worker_poll_seconds, 1 << exponent)
    return min(settings.nexus_test_retry_max_seconds, delay)


def _data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _download_references(bot: Bot, references: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    total = 0
    for reference in references:
        file_size = int(reference.get("file_size") or 0)
        if file_size > MAX_REFERENCE_FILE_BYTES:
            raise NexusProviderError("Один из референсов больше 8 МБ")
        buffer = BytesIO()
        await bot.download(str(reference.get("file_id") or ""), destination=buffer)
        content = buffer.getvalue()
        if not content:
            raise NexusProviderError("Не удалось скачать один из референсов из Telegram")
        if len(content) > MAX_REFERENCE_FILE_BYTES:
            raise NexusProviderError("Один из референсов больше 8 МБ")
        total += len(content)
        if total > MAX_REFERENCE_TOTAL_BYTES:
            raise NexusProviderError("Суммарный размер референсов больше 24 МБ")
        values.append(
            _data_url(content, str(reference.get("mime_type") or "image/jpeg"))
        )
    return values


class NexusAdminTaskService:
    @staticmethod
    async def enqueue(
        session: AsyncSession,
        *,
        telegram_id: int,
        chat_id: int,
        prompt: str,
        references: list[dict[str, Any]],
        aspect_ratio: str,
        image_size: str,
        idempotency_key: str,
    ) -> NexusAdminTask:
        task_id = uuid.uuid4()
        result = await session.execute(
            pg_insert(NexusAdminTask)
            .values(
                id=task_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                status="queued",
                prompt=prompt,
                references=references,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                idempotency_key=idempotency_key,
                attempts=0,
                available_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[NexusAdminTask.idempotency_key])
            .returning(NexusAdminTask.id)
        )
        inserted_id = result.scalar_one_or_none()
        resolved_id = inserted_id or await session.scalar(
            select(NexusAdminTask.id).where(
                NexusAdminTask.idempotency_key == idempotency_key
            )
        )
        if resolved_id is None:
            raise RuntimeError("Nexus task idempotency row disappeared after insert")
        task = await session.get(NexusAdminTask, resolved_id)
        if task is None:
            raise RuntimeError("Nexus task could not be reloaded after insert")
        return task

    @staticmethod
    async def claim(session: AsyncSession) -> uuid.UUID | None:
        now = utcnow()
        task = await session.scalar(
            select(NexusAdminTask)
            .where(
                NexusAdminTask.status.not_in(_TERMINAL_STATUSES),
                NexusAdminTask.available_at <= now,
                or_(
                    NexusAdminTask.lease_until.is_(None),
                    NexusAdminTask.lease_until <= now,
                ),
            )
            .order_by(NexusAdminTask.available_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None
        task.lease_until = now + timedelta(
            seconds=settings.nexus_test_task_lease_seconds
        )
        await session.commit()
        return task.id

    @staticmethod
    async def _save_retry(task_id: uuid.UUID, exc: Exception) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.attempts += 1
            if task.status != "failure_pending":
                task.error = str(exc)[:4000]
            task.lease_until = None
            task.available_at = utcnow() + timedelta(
                seconds=_retry_delay(task.attempts)
            )
            await session.commit()

    @staticmethod
    async def _set_failure_pending(task_id: uuid.UUID, error: str) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.status = "failure_pending"
            task.error = error[:4000]
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

    @staticmethod
    async def _submit(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or task.external_id:
                return
            prompt = task.prompt
            references = list(task.references or [])
            aspect_ratio = task.aspect_ratio
            image_size = task.image_size
            idempotency_key = task.idempotency_key

        image_urls = await _download_references(bot, references)
        client = NexusClient(
            settings.nexus_api_key,
            settings.nexus_api_base_url,
        )
        try:
            external_id = await client.create_nano_banana_pro(
                prompt=prompt,
                image_urls=image_urls,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                idempotency_key=idempotency_key,
            )
        finally:
            await client.aclose()

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            if task.external_id and task.external_id != external_id:
                raise NexusProviderError(
                    f"Nexus task identity changed: {task.external_id} != {external_id}"
                )
            task.external_id = external_id
            task.status = "generating"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow() + timedelta(
                seconds=settings.nexus_test_worker_poll_seconds
            )
            await session.commit()
        logger.info(
            "nexus_admin_task_submitted",
            extra={"task_id": str(task_id), "provider_task_id": external_id},
        )

    @staticmethod
    async def _poll(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or not task.external_id:
                return
            external_id = task.external_id

        client = NexusClient(
            settings.nexus_api_key,
            settings.nexus_api_base_url,
        )
        try:
            provider_task = await client.get_task(external_id)
        finally:
            await client.aclose()

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            if provider_task.status == "completed":
                if not provider_task.image_urls:
                    raise NexusProviderError(
                        f"NexusAPI task {external_id} completed without image URL"
                    )
                task.result_url = provider_task.image_urls[0]
                task.status = "delivering"
                task.error = None
                task.available_at = utcnow()
            elif provider_task.status == "failed":
                task.status = "failure_pending"
                task.error = (
                    provider_task.error or f"NexusAPI task {external_id} failed"
                )[:4000]
                task.available_at = utcnow()
            else:
                task.status = "generating"
                task.available_at = utcnow() + timedelta(
                    seconds=settings.nexus_test_worker_poll_seconds
                )
            task.lease_until = None
            await session.commit()

        if provider_task.status == "failed":
            await NexusAdminTaskService._deliver_failure(task_id, bot)

    @staticmethod
    async def _deliver_failure(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.status != "failure_pending":
                return
            chat_id = task.chat_id
            error = task.error or "NexusAPI завершил задачу с ошибкой"
            external_id = task.external_id or ""

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ NexusAPI · Nano Banana Pro\n"
                f"{error[:1000]}"
                + (f"\nTask: {external_id}" if external_id else "")
            ),
        )

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status != "failure_pending":
                return
            task.status = "failed"
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()
        logger.info(
            "nexus_admin_failure_delivered",
            extra={"task_id": str(task_id), "provider_task_id": external_id},
        )

    @staticmethod
    async def _deliver(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if (
                task is None
                or task.status in _TERMINAL_STATUSES
                or not task.result_url
            ):
                return
            chat_id = task.chat_id
            result_url = task.result_url
            external_id = task.external_id or ""
            image_size = task.image_size
            aspect_ratio = task.aspect_ratio
            reference_count = len(task.references or [])

        caption = (
            "✅ NexusAPI · Nano Banana Pro\n"
            f"Task: {external_id}\n"
            f"Референсы: {reference_count}\n"
            f"Параметры: {image_size} · {aspect_ratio}"
        )
        try:
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=result_url,
                caption=caption,
            )
        except TelegramAPIError:
            message = await bot.send_message(
                chat_id=chat_id,
                text=f"{caption}\n\nРезультат: {result_url}",
            )

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None:
                return
            task.status = "succeeded"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()
        logger.info(
            "nexus_admin_task_delivered",
            extra={
                "task_id": str(task_id),
                "provider_task_id": external_id,
                "telegram_message_id": getattr(message, "message_id", ""),
            },
        )

    @classmethod
    async def process(cls, task_id: uuid.UUID, bot: Bot) -> None:
        try:
            async with SessionFactory() as session:
                task = await session.get(NexusAdminTask, task_id)
                if task is None or task.status in _TERMINAL_STATUSES:
                    return
                status = task.status
                has_result = bool(task.result_url)
                has_external = bool(task.external_id)
                created_at = task.created_at

            if status == "failure_pending":
                await cls._deliver_failure(task_id, bot)
                return

            if has_result or status == "delivering":
                await cls._deliver(task_id, bot)
                return

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if (
                utcnow() - created_at
            ).total_seconds() > settings.nexus_test_hard_timeout_seconds:
                await cls._set_failure_pending(
                    task_id,
                    (
                        "Nexus task exceeded "
                        f"{settings.nexus_test_hard_timeout_seconds}s hard timeout"
                    ),
                )
                await cls._deliver_failure(task_id, bot)
                return

            if has_external:
                await cls._poll(task_id, bot)
            else:
                await cls._submit(task_id, bot)
        except (NexusProviderError, TelegramAPIError, OSError) as exc:
            logger.warning(
                "nexus_admin_task_retry",
                extra={"task_id": str(task_id), "error": str(exc)},
            )
            await cls._save_retry(task_id, exc)
        except Exception as exc:
            logger.exception(
                "nexus_admin_task_crashed",
                extra={"task_id": str(task_id)},
            )
            await cls._save_retry(task_id, exc)
