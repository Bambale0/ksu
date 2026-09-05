from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.media_models import MediaAsset, MediaIngestJob
from app.db.models import Generation
from app.services.local_media_storage import (
    LOCAL_MEDIA_BUCKET,
    LocalMediaStorage,
    LocalMediaStorageError,
)
from app.services.media_assets import MediaIngestError, MediaIngestService

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_ALLOWED_AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay_seconds(attempt: int) -> int:
    return min(900, 2 ** max(2, min(attempt + 1, 9)))


@dataclass(frozen=True, slots=True)
class ClaimedMusicMediaJob:
    asset_id: uuid.UUID
    attempts: int


@dataclass(frozen=True, slots=True)
class DownloadedAudio:
    path: Path
    size_bytes: int
    sha256: str
    content_type: str
    suffix: str


class MusicMediaAssetService:
    @classmethod
    async def enqueue_results(
        cls,
        session: AsyncSession,
        generation: Generation,
        result_urls: list[str],
    ) -> int:
        created = 0
        for ordinal, source_url in enumerate(dict.fromkeys(result_urls)):
            if not source_url:
                continue
            asset_id = await session.scalar(
                pg_insert(MediaAsset)
                .values(
                    id=uuid.uuid4(),
                    generation_id=generation.id,
                    user_id=generation.user_id,
                    ordinal=ordinal,
                    source_url=source_url,
                    status="audio_pending",
                )
                .on_conflict_do_nothing(
                    index_elements=[MediaAsset.generation_id, MediaAsset.ordinal]
                )
                .returning(MediaAsset.id)
            )
            if asset_id is None:
                asset_id = await session.scalar(
                    select(MediaAsset.id).where(
                        MediaAsset.generation_id == generation.id,
                        MediaAsset.ordinal == ordinal,
                    )
                )
            if asset_id is None:
                continue
            inserted_job = await session.scalar(
                pg_insert(MediaIngestJob)
                .values(
                    asset_id=asset_id,
                    status="audio_pending",
                    attempts=0,
                    available_at=utcnow(),
                )
                .on_conflict_do_nothing(index_elements=[MediaIngestJob.asset_id])
                .returning(MediaIngestJob.asset_id)
            )
            if inserted_job is not None:
                created += 1
        return created


class MusicMediaIngestQueue:
    @staticmethod
    async def claim(session: AsyncSession) -> ClaimedMusicMediaJob | None:
        now = utcnow()
        row = await session.scalar(
            select(MediaIngestJob)
            .where(
                MediaIngestJob.available_at <= now,
                or_(
                    MediaIngestJob.status == "audio_pending",
                    and_(
                        MediaIngestJob.status == "audio_processing",
                        MediaIngestJob.lease_until.is_not(None),
                        MediaIngestJob.lease_until < now,
                    ),
                ),
            )
            .order_by(MediaIngestJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        row.status = "audio_processing"
        row.attempts += 1
        row.lease_until = now + timedelta(seconds=settings.media_ingest_lease_seconds)
        row.last_error = None
        await session.commit()
        return ClaimedMusicMediaJob(asset_id=row.asset_id, attempts=row.attempts)

    @staticmethod
    async def complete(session: AsyncSession, asset_id: uuid.UUID) -> None:
        row = await session.get(MediaIngestJob, asset_id, with_for_update=True)
        if row is None:
            return
        row.status = "completed"
        row.lease_until = None
        row.completed_at = utcnow()
        row.last_error = None
        await session.commit()

    @staticmethod
    async def defer_without_attempt(
        session: AsyncSession,
        *,
        asset_id: uuid.UUID,
        error: str,
        delay_seconds: int = 300,
    ) -> None:
        row = await session.get(MediaIngestJob, asset_id, with_for_update=True)
        asset = await session.get(MediaAsset, asset_id, with_for_update=True)
        if row is None or asset is None:
            return
        row.status = "audio_pending"
        row.attempts = max(0, row.attempts - 1)
        row.lease_until = None
        row.available_at = utcnow() + timedelta(seconds=max(30, delay_seconds))
        row.last_error = error[:4000]
        asset.status = "audio_pending"
        asset.error = error[:4000]
        await session.commit()

    @staticmethod
    async def release_or_fail(
        session: AsyncSession,
        *,
        asset_id: uuid.UUID,
        attempts: int,
        error: str,
    ) -> None:
        row = await session.get(MediaIngestJob, asset_id, with_for_update=True)
        asset = await session.get(MediaAsset, asset_id, with_for_update=True)
        if row is None or asset is None:
            return
        row.lease_until = None
        row.last_error = error[:4000]
        asset.error = error[:4000]
        if attempts >= settings.media_ingest_max_attempts:
            row.status = "failed"
            row.completed_at = utcnow()
            asset.status = "failed"
        else:
            row.status = "audio_pending"
            row.available_at = utcnow() + timedelta(seconds=retry_delay_seconds(attempts))
            asset.status = "audio_pending"
        await session.commit()


class MusicMediaIngestService:
    @classmethod
    async def process_one(cls, session: AsyncSession) -> bool:
        claim = await MusicMediaIngestQueue.claim(session)
        if claim is None:
            return False
        asset = await session.get(MediaAsset, claim.asset_id)
        if asset is None:
            await MusicMediaIngestQueue.complete(session, claim.asset_id)
            return True
        if asset.status == "ready" and asset.object_key:
            await MusicMediaIngestQueue.complete(session, claim.asset_id)
            return True

        try:
            downloaded = await cls._download(asset.source_url)
            try:
                key = cls._object_key(asset, downloaded)
                await asyncio.to_thread(
                    LocalMediaStorage.persist_file,
                    downloaded.path,
                    key=key,
                )
            finally:
                downloaded.path.unlink(missing_ok=True)

            locked_asset = await session.get(MediaAsset, asset.id, with_for_update=True)
            if locked_asset is None:
                return True
            locked_asset.status = "ready"
            locked_asset.bucket = LOCAL_MEDIA_BUCKET
            locked_asset.object_key = key
            locked_asset.content_type = downloaded.content_type
            locked_asset.size_bytes = downloaded.size_bytes
            locked_asset.sha256 = downloaded.sha256
            locked_asset.etag = None
            locked_asset.error = None
            await session.commit()
            await MusicMediaIngestQueue.complete(session, asset.id)
            return True
        except LocalMediaStorageError as exc:
            await MusicMediaIngestQueue.defer_without_attempt(
                session,
                asset_id=claim.asset_id,
                error=str(exc),
            )
            return True
        except (MediaIngestError, httpx.HTTPError) as exc:
            await MusicMediaIngestQueue.release_or_fail(
                session,
                asset_id=claim.asset_id,
                attempts=claim.attempts,
                error=str(exc),
            )
            return True
        except Exception as exc:
            await MusicMediaIngestQueue.release_or_fail(
                session,
                asset_id=claim.asset_id,
                attempts=claim.attempts,
                error=f"unexpected music media ingest error: {exc}",
            )
            raise

    @classmethod
    async def _download(cls, source_url: str) -> DownloadedAudio:
        current_url = source_url
        timeout = httpx.Timeout(
            connect=settings.media_ingest_connect_timeout_seconds,
            read=settings.media_ingest_read_timeout_seconds,
            write=30.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "ksu-music-ingest/1.0"},
        ) as client:
            for _ in range(settings.media_ingest_max_redirects + 1):
                await MediaIngestService._validate_public_https_url(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise MediaIngestError("Audio source redirect has no Location header")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise MediaIngestError("Audio source returned invalid Content-Length") from exc
                        if declared_size > settings.media_ingest_max_bytes:
                            raise MediaIngestError("Audio source exceeds MEDIA_INGEST_MAX_BYTES")

                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    suffix = cls._suffix_for(current_url, content_type)
                    if not cls._allowed_content_type(content_type, suffix):
                        raise MediaIngestError(
                            f"Unsupported audio content type: {content_type or 'unknown'}"
                        )
                    if not content_type or content_type == "application/octet-stream":
                        content_type = mimetypes.guess_type(f"file{suffix}")[0] or "audio/mpeg"

                    handle = tempfile.NamedTemporaryFile(
                        prefix="ksu-music-",
                        suffix=suffix,
                        delete=False,
                    )
                    path = Path(handle.name)
                    digest = hashlib.sha256()
                    size = 0
                    try:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > settings.media_ingest_max_bytes:
                                raise MediaIngestError("Audio source exceeds MEDIA_INGEST_MAX_BYTES")
                            digest.update(chunk)
                            handle.write(chunk)
                    except Exception:
                        handle.close()
                        path.unlink(missing_ok=True)
                        raise
                    handle.close()
                    if size <= 0:
                        path.unlink(missing_ok=True)
                        raise MediaIngestError("Audio source is empty")
                    return DownloadedAudio(
                        path=path,
                        size_bytes=size,
                        sha256=digest.hexdigest(),
                        content_type=content_type,
                        suffix=suffix,
                    )
            raise MediaIngestError("Too many audio source redirects")

    @staticmethod
    def _allowed_content_type(content_type: str, suffix: str) -> bool:
        return content_type.startswith("audio/") or (
            content_type in {"", "application/octet-stream"} and suffix in _ALLOWED_AUDIO_SUFFIXES
        )

    @staticmethod
    def _suffix_for(url: str, content_type: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in _ALLOWED_AUDIO_SUFFIXES:
            return suffix
        guessed = mimetypes.guess_extension(content_type) if content_type else None
        aliases = {".oga": ".ogg", ".mpga": ".mp3"}
        guessed = aliases.get(str(guessed), guessed)
        return str(guessed) if guessed in _ALLOWED_AUDIO_SUFFIXES else ".mp3"

    @staticmethod
    def _object_key(asset: MediaAsset, media: DownloadedAudio) -> str:
        return (
            f"generations/{asset.user_id}/{asset.generation_id}/"
            f"{asset.ordinal:03d}-{media.sha256[:24]}{media.suffix}"
        )
