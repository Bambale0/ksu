from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.services.media_assets import MediaIngestService
from app.services.music_media import MusicMediaIngestService
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured

logger = logging.getLogger(__name__)


def _suffix(value: str | None) -> str:
    if not value:
        return ".bin"
    suffix = Path(value.split("?", 1)[0]).suffix.lower()
    if not suffix or len(suffix) > 9:
        return ".bin"
    return suffix


def _filename(generation: Generation, path: Path) -> str:
    suffix = path.suffix.lower() or ".bin"
    return f"generation-{generation.id}{suffix}"


async def _ready_asset(
    session: AsyncSession,
    generation: Generation,
) -> MediaAsset | None:
    return await session.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.generation_id == generation.id,
            MediaAsset.user_id == generation.user_id,
            MediaAsset.status == "ready",
            MediaAsset.object_key.is_not(None),
            MediaAsset.bucket.is_not(None),
        )
        .order_by(MediaAsset.ordinal.asc())
        .limit(1)
    )


async def _send_native(  # type: ignore[no-untyped-def]
    bot: Bot,
    *,
    chat_id: int,
    media_type: str,
    media,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None,
):
    if media_type == "video":
        return await bot.send_video(
            chat_id=chat_id,
            video=media,
            caption=caption,
            reply_markup=reply_markup,
            supports_streaming=True,
        )
    if media_type == "audio":
        return await bot.send_audio(
            chat_id=chat_id,
            audio=media,
            caption=caption,
            reply_markup=reply_markup,
        )
    return await bot.send_photo(
        chat_id=chat_id,
        photo=media,
        caption=caption,
        reply_markup=reply_markup,
    )


async def _download_original(
    *,
    generation: Generation,
    media_type: str,
    result_url: str,
    ready_asset: MediaAsset | None,
    storage: ObjectStorage | None,
) -> Path:
    if (
        ready_asset is not None
        and storage is not None
        and ready_asset.object_key
        and ready_asset.bucket
    ):
        handle = tempfile.NamedTemporaryFile(
            prefix="ksu-telegram-generation-",
            suffix=_suffix(ready_asset.object_key),
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        try:
            await storage.download_file(
                path,
                key=ready_asset.object_key,
                bucket=ready_asset.bucket,
            )
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError("Durable generation media is empty")
            return path
        except Exception:
            path.unlink(missing_ok=True)
            raise

    if media_type == "audio":
        downloaded_audio = await MusicMediaIngestService._download(result_url)
        return downloaded_audio.path
    downloaded = await MediaIngestService._download(result_url)
    return downloaded.path


async def send_generation_result_media(  # type: ignore[no-untyped-def]
    bot: Bot,
    *,
    session: AsyncSession,
    chat_id: int,
    generation: Generation,
    media_type: str,
    result_url: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None,
):
    """Deliver generated media without silently degrading to text-only.

    Telegram first gets a normal remote-URL send for the fast path. A media
    validation/fetch rejection triggers a server-side original download and
    direct upload. Network errors, rate limits and recipient errors are not
    misclassified as media-format failures and escape immediately to the durable
    notification outbox. Ready durable media in object storage is preferred so
    an expired provider URL cannot break a later retry.
    """

    asset = await _ready_asset(session, generation)
    storage: ObjectStorage | None = None
    remote_url = result_url
    if asset is not None and asset.object_key and asset.bucket:
        try:
            storage = ObjectStorage()
            remote_url = storage.presign_get(key=asset.object_key, bucket=asset.bucket)
        except ObjectStorageNotConfigured:
            storage = None

    try:
        return await _send_native(
            bot,
            chat_id=chat_id,
            media_type=media_type,
            media=remote_url,
            caption=caption,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        logger.info(
            "generation_notification_remote_media_failed",
            extra={
                "generation_id": str(generation.id),
                "media_type": media_type,
                "error": str(exc),
                "durable_asset": asset is not None,
            },
        )

    path = await _download_original(
        generation=generation,
        media_type=media_type,
        result_url=result_url,
        ready_asset=asset,
        storage=storage,
    )
    try:
        local_media = FSInputFile(path, filename=_filename(generation, path))
        try:
            return await _send_native(
                bot,
                chat_id=chat_id,
                media_type=media_type,
                media=local_media,
                caption=caption,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            logger.info(
                "generation_notification_native_upload_failed",
                extra={
                    "generation_id": str(generation.id),
                    "media_type": media_type,
                    "error": str(exc),
                },
            )
            return await bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(path, filename=_filename(generation, path)),
                caption=caption,
                reply_markup=reply_markup,
            )
    finally:
        path.unlink(missing_ok=True)
