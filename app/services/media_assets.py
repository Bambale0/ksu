from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import mimetypes
import socket
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import and_, func, or_, select
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
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay_seconds(attempt: int) -> int:
    return min(900, 2 ** max(2, min(attempt + 1, 9)))


@dataclass(frozen=True, slots=True)
class ClaimedMediaJob:
    asset_id: uuid.UUID
    attempts: int


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    path: Path
    size_bytes: int
    sha256: str
    content_type: str
    suffix: str


class UnsafeMediaSource(RuntimeError):
    pass


class MediaIngestError(RuntimeError):
    pass


class MediaAssetService:
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
                    status="pending",
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
                    status="pending",
                    attempts=0,
                    available_at=utcnow(),
                )
                .on_conflict_do_nothing(index_elements=[MediaIngestJob.asset_id])
                .returning(MediaIngestJob.asset_id)
            )
            if inserted_job is not None:
                created += 1
        return created

    @classmethod
    async def ensure_legacy(cls, session: AsyncSession, *, limit: int = 100) -> int:
        generations = list(
            (
                await session.scalars(
                    select(Generation)
                    .outerjoin(MediaAsset, MediaAsset.generation_id == Generation.id)
                    .where(
                        Generation.status == "succeeded",
                        MediaAsset.id.is_(None),
                        Generation.result_url.is_not(None),
                    )
                    .order_by(Generation.created_at.asc())
                    .limit(limit)
                )
            ).all()
        )
        created = 0
        for generation in generations:
            raw = (generation.parameters or {}).get("_result_urls")
            result_urls = [str(item) for item in raw] if isinstance(raw, list) else []
            if generation.result_url and generation.result_url not in result_urls:
                result_urls.insert(0, generation.result_url)
            created += await cls.enqueue_results(session, generation, result_urls)
        if generations:
            await session.commit()
        return created

    @staticmethod
    async def ready_assets_for_generations(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        generation_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[MediaAsset]]:
        if not generation_ids:
            return {}
        rows = list(
            (
                await session.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.user_id == user_id,
                        MediaAsset.generation_id.in_(generation_ids),
                        MediaAsset.status == "ready",
                        MediaAsset.object_key.is_not(None),
                        MediaAsset.bucket.is_not(None),
                    )
                    .order_by(MediaAsset.generation_id, MediaAsset.ordinal)
                )
            ).all()
        )
        grouped: dict[uuid.UUID, list[MediaAsset]] = {}
        for row in rows:
            grouped.setdefault(row.generation_id, []).append(row)
        return grouped

    @staticmethod
    def public_view(
        asset: MediaAsset,
        storage: ObjectStorage | None = None,
        *,
        server_route: bool = False,
    ) -> dict[str, object]:
        if not asset.object_key or not asset.bucket:
            raise MediaIngestError("Media asset is not ready")
        route_url = f"/api/v1/media/{asset.id}/public"
        download_url = f"/api/v1/media/{asset.id}/download"
        if LocalMediaStorage.is_local_bucket(asset.bucket):
            url = (
                route_url
                if server_route
                else LocalMediaStorage.signed_view_url(
                    asset_id=asset.id,
                    key=asset.object_key,
                )
            )
        elif server_route:
            url = route_url
        elif ObjectStorage.configured():
            storage = storage or ObjectStorage()
            try:
                url = storage.presign_get(key=asset.object_key, bucket=asset.bucket)
            except ObjectStorageNotConfigured:
                url = asset.source_url
        else:
            # Old S3 rows stay backwards-compatible when an operator intentionally
            # removes legacy S3 configuration: use the original provider URL while
            # it remains alive instead of hiding an otherwise successful result.
            url = asset.source_url
        return {
            "id": str(asset.id),
            "url": url,
            "download_url": download_url,
            "public_url": route_url,
            "content_type": asset.content_type,
            "size_bytes": asset.size_bytes,
            "ordinal": asset.ordinal,
        }


class MediaIngestQueue:
    @staticmethod
    async def claim(session: AsyncSession) -> ClaimedMediaJob | None:
        now = utcnow()
        row = await session.scalar(
            select(MediaIngestJob)
            .where(
                MediaIngestJob.available_at <= now,
                or_(
                    MediaIngestJob.status == "pending",
                    and_(
                        MediaIngestJob.status == "processing",
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
        row.status = "processing"
        row.attempts += 1
        row.lease_until = now + timedelta(seconds=settings.media_ingest_lease_seconds)
        row.last_error = None
        await session.commit()
        return ClaimedMediaJob(asset_id=row.asset_id, attempts=row.attempts)

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
        row.status = "pending"
        row.attempts = max(0, row.attempts - 1)
        row.lease_until = None
        row.available_at = utcnow() + timedelta(seconds=max(30, delay_seconds))
        row.last_error = error[:4000]
        asset.status = "pending"
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
            row.status = "pending"
            row.available_at = utcnow() + timedelta(seconds=retry_delay_seconds(attempts))
            asset.status = "pending"
        await session.commit()


class MediaIngestService:
    @classmethod
    async def process_one(cls, session: AsyncSession) -> bool:
        claim = await MediaIngestQueue.claim(session)
        if claim is None:
            return False
        asset = await session.get(MediaAsset, claim.asset_id)
        if asset is None:
            await MediaIngestQueue.complete(session, claim.asset_id)
            return True
        if asset.status == "ready" and asset.object_key:
            await MediaIngestQueue.complete(session, claim.asset_id)
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
            await MediaIngestQueue.complete(session, asset.id)
            return True
        except LocalMediaStorageError as exc:
            # Host storage availability is an operator state. Keep retrying without
            # burning the media retry budget while the provider URL is still usable.
            await MediaIngestQueue.defer_without_attempt(
                session,
                asset_id=claim.asset_id,
                error=str(exc),
            )
            return True
        except (UnsafeMediaSource, MediaIngestError, httpx.HTTPError) as exc:
            await MediaIngestQueue.release_or_fail(
                session,
                asset_id=claim.asset_id,
                attempts=claim.attempts,
                error=str(exc),
            )
            return True
        except Exception as exc:
            await MediaIngestQueue.release_or_fail(
                session,
                asset_id=claim.asset_id,
                attempts=claim.attempts,
                error=f"unexpected media ingest error: {exc}",
            )
            raise

    @classmethod
    async def _download(cls, source_url: str) -> DownloadedMedia:
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
            headers={"User-Agent": "ksu-media-ingest/1.0"},
        ) as client:
            for _ in range(settings.media_ingest_max_redirects + 1):
                await cls._validate_public_https_url(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise MediaIngestError("Media source redirect has no Location header")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise MediaIngestError("Media source returned invalid Content-Length") from exc
                        if declared_size > settings.media_ingest_max_bytes:
                            raise MediaIngestError("Media source exceeds MEDIA_INGEST_MAX_BYTES")

                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    suffix = cls._suffix_for(current_url, content_type)
                    if not cls._allowed_content_type(content_type, suffix):
                        raise MediaIngestError(
                            f"Unsupported media content type: {content_type or 'unknown'}"
                        )
                    if not content_type or content_type == "application/octet-stream":
                        content_type = (
                            mimetypes.guess_type(f"file{suffix}")[0] or "application/octet-stream"
                        )

                    handle = tempfile.NamedTemporaryFile(
                        prefix="ksu-media-",
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
                                raise MediaIngestError("Media source exceeds MEDIA_INGEST_MAX_BYTES")
                            digest.update(chunk)
                            handle.write(chunk)
                    except Exception:
                        handle.close()
                        path.unlink(missing_ok=True)
                        raise
                    handle.close()
                    if size <= 0:
                        path.unlink(missing_ok=True)
                        raise MediaIngestError("Media source is empty")
                    return DownloadedMedia(
                        path=path,
                        size_bytes=size,
                        sha256=digest.hexdigest(),
                        content_type=content_type,
                        suffix=suffix,
                    )
            raise MediaIngestError("Too many media source redirects")

    @staticmethod
    def _allowed_content_type(content_type: str, suffix: str) -> bool:
        return (
            content_type.startswith("image/")
            or content_type.startswith("video/")
            or (content_type in {"", "application/octet-stream"} and suffix in _ALLOWED_SUFFIXES)
        )

    @staticmethod
    def _suffix_for(url: str, content_type: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in _ALLOWED_SUFFIXES:
            return suffix
        guessed = mimetypes.guess_extension(content_type) if content_type else None
        if guessed == ".jpe":
            guessed = ".jpg"
        return guessed if guessed in _ALLOWED_SUFFIXES else ".bin"

    @staticmethod
    def _object_key(asset: MediaAsset, media: DownloadedMedia) -> str:
        return (
            f"generations/{asset.user_id}/{asset.generation_id}/"
            f"{asset.ordinal:03d}-{media.sha256[:24]}{media.suffix}"
        )

    @classmethod
    async def _validate_public_https_url(cls, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise UnsafeMediaSource("Media source must be an unauthenticated public HTTPS URL")
        host = parsed.hostname
        try:
            direct = ipaddress.ip_address(host)
            addresses = [direct]
        except ValueError:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
            addresses = []
            for info in infos:
                try:
                    addresses.append(ipaddress.ip_address(info[4][0]))
                except ValueError:
                    continue
        if not addresses:
            raise UnsafeMediaSource("Media source hostname did not resolve")
        if any(not address.is_global for address in addresses):
            raise UnsafeMediaSource("Media source resolves to a non-public address")


async def media_queue_snapshot(session: AsyncSession) -> dict[str, int | float]:
    pending = int(
        await session.scalar(
            select(func.count()).select_from(MediaIngestJob).where(
                MediaIngestJob.status.in_(("pending", "processing"))
            )
        )
        or 0
    )
    oldest = await session.scalar(
        select(func.min(MediaIngestJob.created_at)).where(
            MediaIngestJob.status.in_(("pending", "processing"))
        )
    )
    age = 0.0
    if oldest is not None:
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age = max(0.0, (utcnow() - oldest).total_seconds())
    return {"pending": pending, "oldest_seconds": age}
