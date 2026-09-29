from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

from app.core.config import settings
from app.db.nexus_models import NexusAdminTask
from app.db.session import SessionFactory
from app.providers.neironych import NeironychClient, NeironychProviderError
from app.services.reference_static import ReferenceStaticStorage

logger = logging.getLogger(__name__)


def _storage_kind(reference_kind: str) -> str:
    if reference_kind in {"start_image", "end_image"}:
        return "image"
    if reference_kind in {"image", "video", "audio"}:
        return reference_kind
    raise NeironychProviderError(f"Unsupported admin test media kind: {reference_kind}")


def _absolute_public_url(value: str) -> str:
    parsed = urlsplit(str(value or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise NeironychProviderError(
            "PUBLIC_BASE_URL must be an absolute HTTPS URL for Seedance test references"
        )
    return value


def _safe_local_path(value: str | None) -> Path | None:
    if not value:
        return None
    try:
        candidate = Path(value).resolve()
        candidate.relative_to(ReferenceStaticStorage.root())
    except (OSError, ValueError):
        return None
    return candidate


async def cleanup_staged_media(task_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        task = await session.get(NexusAdminTask, task_id)
        references = list(task.references or []) if task is not None else []

    for reference in references:
        path = _safe_local_path(str(reference.get("local_path") or ""))
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "admin_test_media_cleanup_failed",
                extra={"task_id": str(task_id), "path_name": path.name},
            )


async def _stage_one(
    *,
    task_id: uuid.UUID,
    bot: Bot,
    reference: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    if reference.get("url"):
        staged = dict(reference)
        staged["url"] = _absolute_public_url(str(staged["url"]))
        return staged, int(staged.get("file_size") or 0)

    file_id = str(reference.get("file_id") or "").strip()
    if not file_id:
        raise NeironychProviderError("Seedance admin test reference has no Telegram file_id")

    declared_size = int(reference.get("file_size") or 0)
    if declared_size > settings.admin_test_media_max_bytes:
        raise NeironychProviderError(
            "Seedance admin test reference exceeds the configured per-file limit"
        )

    kind = _storage_kind(str(reference.get("kind") or ""))
    content_type = str(reference.get("mime_type") or "").split(";", 1)[0].strip().lower()
    if not ReferenceStaticStorage.supports_content_type(content_type, kind=kind):
        raise NeironychProviderError(
            f"Unsupported Seedance admin test {kind} media type: {content_type or 'unknown'}"
        )

    suffix = ReferenceStaticStorage.SAFE_MEDIA_EXTENSIONS.get(content_type, ".bin")
    handle = tempfile.NamedTemporaryFile(
        prefix="ksu-admin-seedance-",
        suffix=suffix,
        delete=False,
    )
    temp_path = Path(handle.name)
    handle.close()

    try:
        with temp_path.open("wb") as output:
            await bot.download(file_id, destination=output)
        size = int(temp_path.stat().st_size)
        if size <= 0:
            raise NeironychProviderError("Telegram returned an empty Seedance test reference")
        if size > settings.admin_test_media_max_bytes:
            raise NeironychProviderError(
                "Seedance admin test reference exceeds the configured per-file limit"
            )

        digest = hashlib.sha256()
        with temp_path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)

        filename = str(reference.get("file_name") or f"reference{suffix}")[:255]
        with temp_path.open("rb") as stream:
            public_url, stored_path, stored_size = ReferenceStaticStorage.persist_stream(
                stream,
                user_id=task_id,
                kind=kind,
                file_hash=digest.hexdigest(),
                filename=filename,
                content_type=content_type,
                expected_size=size,
            )
        staged = dict(reference)
        staged["url"] = _absolute_public_url(public_url)
        staged["local_path"] = str(stored_path)
        staged["file_size"] = stored_size
        return staged, stored_size
    except NeironychProviderError:
        raise
    except (OSError, TelegramAPIError) as exc:
        raise NeironychProviderError(
            f"Unable to stage Seedance admin test media: {exc}",
            retryable=True,
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


async def _stage_references(task_id: uuid.UUID, bot: Bot) -> list[dict[str, Any]]:
    async with SessionFactory() as session:
        task = await session.get(NexusAdminTask, task_id)
        if task is None:
            raise LookupError("Admin test task not found")
        raw_references = list(task.references or [])

    staged: list[dict[str, Any]] = []
    total = 0
    for reference in raw_references:
        item, size = await _stage_one(task_id=task_id, bot=bot, reference=reference)
        total += max(0, int(size))
        if total > settings.admin_test_media_total_max_bytes:
            raise NeironychProviderError(
                "Seedance admin test references exceed the configured total media limit"
            )
        staged.append(item)

    async with SessionFactory() as session:
        task = await session.get(NexusAdminTask, task_id, with_for_update=True)
        if task is None:
            raise LookupError("Admin test task disappeared while staging media")
        task.references = staged
        await session.commit()
    return staged


def _reference_urls(
    references: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str], str | None, str | None]:
    images: list[str] = []
    videos: list[str] = []
    audios: list[str] = []
    start_image: str | None = None
    end_image: str | None = None

    for reference in references:
        url = str(reference.get("url") or "").strip()
        kind = str(reference.get("kind") or "")
        if not url:
            raise NeironychProviderError("Seedance admin test staged media has no public URL")
        if kind == "image":
            images.append(url)
        elif kind == "video":
            videos.append(url)
        elif kind == "audio":
            audios.append(url)
        elif kind == "start_image":
            start_image = url
        elif kind == "end_image":
            end_image = url
        else:
            raise NeironychProviderError(f"Unsupported staged media kind: {kind}")

    return images, videos, audios, start_image, end_image


class NeironychAdminTaskRuntime:
    @staticmethod
    async def submit(task_id: uuid.UUID, bot: Bot) -> None:
        references = await _stage_references(task_id, bot)

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or task.external_id:
                return
            prompt = task.prompt
            model_id = task.model_id
            resolution = task.image_size
            aspect_ratio = task.aspect_ratio
            idempotency_key = task.idempotency_key
            parameters = dict(task.parameters or {})

        images, videos, audios, start_image, end_image = _reference_urls(references)
        duration_raw = parameters.get("duration")
        duration = int(duration_raw) if duration_raw is not None else None
        task_type = str(parameters.get("task_type") or "").strip() or None
        generate_audio_raw = parameters.get("generate_audio")
        generate_audio = (
            bool(generate_audio_raw) if generate_audio_raw is not None else None
        )

        client = NeironychClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            external_id = await client.create_seedance_video(
                model=model_id,
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio or None,
                reference_images=images,
                reference_videos=videos,
                reference_audios=audios,
                start_image=start_image,
                end_image=end_image,
                task_type=task_type,
                generate_audio=generate_audio,
                idempotency_key=idempotency_key,
            )
        finally:
            await client.aclose()

        from app.services.nexus_admin_tasks import utcnow

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in {"succeeded", "failed"}:
                return
            if task.external_id and task.external_id != external_id:
                raise NeironychProviderError(
                    f"Neironych task identity changed: {task.external_id} != {external_id}"
                )
            task.external_id = external_id
            task.status = "generating"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

        logger.info(
            "admin_test_seedance_submitted",
            extra={
                "task_id": str(task_id),
                "provider": "neironych",
                "model": model_id,
                "provider_task_id": external_id,
            },
        )

    @staticmethod
    async def poll(task_id: uuid.UUID) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if task is None or not task.external_id:
                return
            external_id = task.external_id

        client = NeironychClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            provider_task = await client.get_video(external_id)
        finally:
            await client.aclose()

        from app.services.nexus_admin_tasks import utcnow

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None or task.status in {"succeeded", "failed"}:
                return
            if provider_task.succeeded:
                task.status = "delivering"
                task.error = None
                task.available_at = utcnow()
            elif provider_task.failed:
                task.status = "failure_pending"
                task.error = (
                    provider_task.error
                    or f"Neironych task {external_id} failed with status {provider_task.status}"
                )[:4000]
                task.available_at = utcnow()
            else:
                task.status = "generating"
                task.error = None
                task.available_at = utcnow()
            task.lease_until = None
            await session.commit()

    @staticmethod
    async def deliver(task_id: uuid.UUID, bot: Bot) -> None:
        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id)
            if (
                task is None
                or task.status in {"succeeded", "failed"}
                or not task.external_id
            ):
                return
            chat_id = task.chat_id
            external_id = task.external_id
            model_id = task.model_id
            resolution = task.image_size
            aspect_ratio = task.aspect_ratio
            parameters = dict(task.parameters or {})
            reference_count = len(task.references or [])

        handle = tempfile.NamedTemporaryFile(
            prefix="ksu-seedance-result-",
            suffix=".mp4",
            delete=False,
        )
        result_path = Path(handle.name)
        handle.close()
        client = NeironychClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            await client.download_video(
                external_id,
                result_path,
                max_bytes=settings.admin_test_result_max_bytes,
            )
        finally:
            await client.aclose()

        duration = parameters.get("duration")
        duration_text = "source" if duration in (None, -1) else f"{duration}s"
        caption = (
            f"✅ Нейроныч · {model_id}\n"
            f"Task: {external_id}\n"
            f"Референсы: {reference_count}\n"
            f"Параметры: {resolution} · {aspect_ratio or 'auto'} · {duration_text}"
        )
        try:
            try:
                message = await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(result_path),
                    caption=caption,
                    supports_streaming=True,
                )
            except TelegramAPIError:
                logger.info(
                    "admin_test_seedance_send_video_failed",
                    extra={"task_id": str(task_id), "provider_task_id": external_id},
                )
                message = await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(result_path),
                    caption=caption,
                )
        finally:
            result_path.unlink(missing_ok=True)

        from app.services.nexus_admin_tasks import utcnow

        async with SessionFactory() as session:
            task = await session.get(NexusAdminTask, task_id, with_for_update=True)
            if task is None:
                return
            task.status = "succeeded"
            task.error = None
            task.lease_until = None
            task.available_at = utcnow()
            await session.commit()

        await cleanup_staged_media(task_id)
        logger.info(
            "admin_test_seedance_delivered",
            extra={
                "task_id": str(task_id),
                "provider_task_id": external_id,
                "telegram_message_id": getattr(message, "message_id", ""),
            },
        )
