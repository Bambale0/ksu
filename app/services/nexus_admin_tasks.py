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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.nexus_models import NexusAdminTask
from app.db.session import SessionFactory
from app.providers.nexus import NexusClient, NexusProviderError

logger = logging.getLogger(__name__)

MAX_REFERENCE_FILE_BYTES = 8 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 24 * 1024 * 1024
_TERMINAL_STATUSES = {"succeeded", "failed"}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _retry_delay(attempts: int) -> int:
    retry_max: int = settings.nexus_test_retry_max_seconds
    poll_seconds: int = settings.nexus_test_worker_poll_seconds
    exponent = min(max(attempts - 1, 0), 5)
    backoff = 1 << exponent
    delay = max(poll_seconds, backoff)
    return retry_max if retry_max < delay else delay


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
        mime_type = str(reference.get("mime_type") or "image/jpeg")
        values.append(_data_url(content, mime_type))
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
        existing = await session.scalar(
            select(NexusAdminTask).where(NexusAdminTask.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        task = NexusAdminTask(
            telegram_id=telegram_id,
            chat_id=chat_id,
            status="queued",
            prompt=prompt,
            references=references,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            idempotency_key=idempotency_key,
            available_at=utcnow(),
        )
        session.add(task)
        await session.flush()
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
        task.lease_until = now + timedelta(seconds=settings.nexus_test_task_lease_seconds)
        await session.commit()
        return task.id

    @staticmethod
    async def _save_retry(task_id: uuid.UUID, exc: Exception) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.attempts += 1
            task.error = str(exc)[:4000]
            task.lease_until = None
            task.available_at = utcnow() + timedelta(seconds=_retry_delay(task.attempts))
            await session.commit()

    @staticmethod
    async def _mark_failed(task_id: uuid.UUID, error: str) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None:
                return
            task.status = "failed"
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
        client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
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
        logger.info("Nexus admin task submitted job=%s provider_task=%s", task_id, external_id)

    @staticmethod
    async def _poll(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or not task.external_id:
                return
            external_id = task.external_id

        client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
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
                task.status = "failed"
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
            await NexusAdminTaskService._send_failure(task_id, bot)

    @staticmethod
    async def _send_failure(task_id: uuid.UUID, bot: Bot) -> None:
        try:
            async with SessionFactory() as session:
                task = await session.get(NexusAdminTask, task_id)
                if task is None:
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
        except TelegramAPIError:
            logger.exception("Could not deliver Nexus failure for %s", task_id)

    @staticmethod
    async def _deliver(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or not task.result_url:
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
            message = await bot.send_photo(chat_id=chat_id, photo=result_url, caption=caption)
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
            "Nexus admin task delivered job=%s provider_task=%s telegram_message=%s",
            task_id,
            external_id,
            getattr(message, "message_id", ""),
        )

    @classmethod
    async def process(cls, task_id: uuid.UUID, bot: Bot) -> None:
        try:
            async with SessionFactory() as session:
                task = await session.get(NexusAdminTask, task_id)
                if task is None or task.status in _TERMINAL_STATUSES:
                    return
                has_result = bool(task.result_url)
                has_external = bool(task.external_id)
                created_at = task.created_at

            if has_result:
                await cls._deliver(task_id, bot)
                return

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if (utcnow() - created_at).total_seconds() > settings.nexus_test_hard_timeout_seconds:
                await cls._mark_failed(
                    task_id,
                    f"Nexus task exceeded {settings.nexus_test_hard_timeout_seconds}s hard timeout",
                )
                await cls._send_failure(task_id, bot)
                return

            if has_external:
                await cls._poll(task_id, bot)
            else:
                await cls._submit(task_id, bot)
        except (NexusProviderError, TelegramAPIError, OSError) as exc:
            logger.warning("Nexus admin task retry job=%s error=%s", task_id, exc)
            await cls._save_retry(task_id, exc)
        except Exception as exc:
            logger.exception("Nexus admin task crashed job=%s", task_id)
            await cls._save_retry(task_id, exc)
