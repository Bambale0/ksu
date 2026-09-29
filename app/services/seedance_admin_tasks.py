from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.seedance_test_models import SeedanceAdminTask
from app.db.session import SessionFactory
from app.providers.neironych_video import (
    NeironychProviderError,
    NeironychVideoClient,
    is_failure_status,
    is_success_status,
)

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})
_NON_RETRYABLE_HTTP = frozenset({400, 401, 402, 403, 404, 405, 413, 415, 422})


def utcnow() -> datetime:
    return datetime.now(UTC)


def _retry_delay(attempts: int) -> int:
    exponent = min(max(attempts - 1, 0), 5)
    delay = max(settings.nexus_test_worker_poll_seconds, 1 << exponent)
    return min(settings.nexus_test_retry_max_seconds, delay)


class SeedanceAdminTaskService:
    @staticmethod
    async def enqueue(
        session: AsyncSession,
        *,
        telegram_id: int,
        chat_id: int,
        model_name: str,
        request_payload: dict,
        idempotency_key: str,
    ) -> SeedanceAdminTask:
        task_id = uuid.uuid4()
        result = await session.execute(
            pg_insert(SeedanceAdminTask)
            .values(
                id=task_id,
                telegram_id=telegram_id,
                chat_id=chat_id,
                status="queued",
                model_name=model_name,
                request_payload=request_payload,
                idempotency_key=idempotency_key,
                attempts=0,
                available_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[SeedanceAdminTask.idempotency_key])
            .returning(SeedanceAdminTask.id)
        )
        inserted_id = result.scalar_one_or_none()
        resolved_id = inserted_id or await session.scalar(
            select(SeedanceAdminTask.id).where(
                SeedanceAdminTask.idempotency_key == idempotency_key
            )
        )
        if resolved_id is None:
            raise RuntimeError("Seedance task idempotency row disappeared after insert")
        task = await session.get(SeedanceAdminTask, resolved_id)
        if task is None:
            raise RuntimeError("Seedance admin task could not be reloaded")
        return task

    @staticmethod
    async def claim(session: AsyncSession) -> uuid.UUID | None:
        now = utcnow()
        task = await session.scalar(
            select(SeedanceAdminTask)
            .where(
                SeedanceAdminTask.status.not_in(_TERMINAL_STATUSES),
                SeedanceAdminTask.available_at <= now,
                or_(
                    SeedanceAdminTask.lease_until.is_(None),
                    SeedanceAdminTask.lease_until <= now,
                ),
            )
            .order_by(SeedanceAdminTask.available_at.asc())
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
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.attempts += 1
            task.error = str(exc)[:2000]
            task.lease_until = None
            task.available_at = utcnow() + timedelta(seconds=_retry_delay(task.attempts))
            await session.commit()

    @staticmethod
    async def _set_failure_pending(task_id: uuid.UUID, error: str) -> None:
        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.status = "failure_pending"
            task.error = error[:2000]
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

    @staticmethod
    async def _submit(task_id: uuid.UUID) -> None:
        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or task.external_id:
                return
            model_name = task.model_name
            payload = dict(task.request_payload or {})
            idempotency_key = task.idempotency_key

        client = NeironychVideoClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            models = await client.list_models()
            if models and model_name not in models:
                raise NeironychProviderError(
                    f"Модель {model_name} сейчас не включена у провайдера. "
                    f"Доступно: {', '.join(models[:30]) or 'нет моделей'}",
                    status_code=422,
                )
            external_id = await client.create_video(
                model=model_name,
                payload=payload,
                idempotency_key=idempotency_key,
            )
        finally:
            await client.aclose()

        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            if task.external_id and task.external_id != external_id:
                raise NeironychProviderError(
                    f"Seedance request identity changed: {task.external_id} != {external_id}"
                )
            task.external_id = external_id
            task.status = "generating"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow() + timedelta(seconds=settings.nexus_test_worker_poll_seconds)
            await session.commit()

        logger.info(
            "seedance_admin_task_submitted",
            extra={
                "task_id": str(task_id),
                "provider_request_id": external_id,
                "model": model_name,
            },
        )

    @staticmethod
    async def _poll(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id)
            if task is None or task.status in _TERMINAL_STATUSES or not task.external_id:
                return
            external_id = task.external_id

        client = NeironychVideoClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            provider_status, provider_error, _payload = await client.get_video(external_id)
        finally:
            await client.aclose()

        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            if is_success_status(provider_status):
                task.status = "delivering"
                task.error = None
                task.available_at = utcnow()
            elif is_failure_status(provider_status):
                task.status = "failure_pending"
                task.error = (
                    provider_error or f"Seedance request {external_id} failed ({provider_status})"
                )[:2000]
                task.available_at = utcnow()
            else:
                task.status = "generating"
                task.available_at = utcnow() + timedelta(seconds=settings.nexus_test_worker_poll_seconds)
            task.lease_until = None
            await session.commit()

        if is_failure_status(provider_status):
            await SeedanceAdminTaskService._deliver_failure(task_id, bot)

    @staticmethod
    async def _deliver_failure(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id)
            if task is None or task.status != "failure_pending":
                return
            chat_id = task.chat_id
            model_name = task.model_name
            external_id = task.external_id or ""
            error = task.error or "Seedance generation failed"

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ {model_name} · тест\n"
                f"{error[:1200]}"
                + (f"\nRequest: {external_id}" if external_id else "")
            ),
        )

        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None or task.status != "failure_pending":
                return
            task.status = "failed"
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

    @staticmethod
    async def _deliver(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id)
            if (
                task is None
                or task.status in _TERMINAL_STATUSES
                or not task.external_id
            ):
                return
            chat_id = task.chat_id
            external_id = task.external_id
            model_name = task.model_name
            payload = dict(task.request_payload or {})

        suffix = ".mp4"
        handle = tempfile.NamedTemporaryFile(
            prefix="ksu-seedance-admin-",
            suffix=suffix,
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        client = NeironychVideoClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            await client.download_content_to(
                external_id,
                path,
                max_bytes=settings.neironych_test_max_video_bytes,
            )
        finally:
            await client.aclose()

        caption = (
            f"✅ {model_name} · тест\n"
            f"Request: {external_id}\n"
            f"Параметры: {str(payload)[:700]}"
        )
        try:
            message = await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(path),
                caption=caption[:1024],
                supports_streaming=True,
            )
        finally:
            path.unlink(missing_ok=True)

        async with SessionFactory() as session:
            task = await session.get(SeedanceAdminTask, task_id, with_for_update=True)
            if task is None:
                return
            task.status = "succeeded"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

        logger.info(
            "seedance_admin_task_delivered",
            extra={
                "task_id": str(task_id),
                "provider_request_id": external_id,
                "telegram_message_id": getattr(message, "message_id", ""),
                "model": model_name,
            },
        )

    @classmethod
    async def process(cls, task_id: uuid.UUID, bot: Bot) -> None:
        try:
            async with SessionFactory() as session:
                task = await session.get(SeedanceAdminTask, task_id)
                if task is None or task.status in _TERMINAL_STATUSES:
                    return
                status = task.status
                has_external = bool(task.external_id)
                created_at = task.created_at

            if status == "failure_pending":
                await cls._deliver_failure(task_id, bot)
                return
            if status == "delivering":
                await cls._deliver(task_id, bot)
                return

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if (
                utcnow() - created_at
            ).total_seconds() > settings.neironych_test_hard_timeout_seconds:
                await cls._set_failure_pending(
                    task_id,
                    (
                        "Seedance test exceeded "
                        f"{settings.neironych_test_hard_timeout_seconds}s hard timeout"
                    ),
                )
                await cls._deliver_failure(task_id, bot)
                return

            if has_external:
                await cls._poll(task_id, bot)
            else:
                await cls._submit(task_id)
        except NeironychProviderError as exc:
            if exc.status_code in _NON_RETRYABLE_HTTP:
                await cls._set_failure_pending(task_id, str(exc))
                await cls._deliver_failure(task_id, bot)
                return
            logger.warning(
                "seedance_admin_task_retry",
                extra={"task_id": str(task_id), "error": str(exc)[:500]},
            )
            await cls._save_retry(task_id, exc)
        except (TelegramAPIError, OSError) as exc:
            logger.warning(
                "seedance_admin_delivery_retry",
                extra={"task_id": str(task_id), "error": str(exc)[:500]},
            )
            await cls._save_retry(task_id, exc)
        except Exception as exc:
            logger.exception(
                "seedance_admin_task_crashed",
                extra={"task_id": str(task_id)},
            )
            await cls._save_retry(task_id, exc)
