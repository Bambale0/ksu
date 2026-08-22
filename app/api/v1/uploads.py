from __future__ import annotations

import asyncio
import hashlib
from typing import BinaryIO

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.core.config import settings
from app.providers.kie import KieProviderError
from app.providers.kie_uploads import KieUploadClient
from app.services.abuse_protection import AbuseProtectionService
from app.services.media_probe import MediaProbe, probe_media_stream
from app.services.references import ReferenceService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MEDIA_PREFIXES = ("image/", "video/", "audio/")


def _upload_size(file: UploadFile) -> int:
    if file.size is not None:
        return int(file.size)
    # Starlette already spooled the multipart part by the time the endpoint runs.
    # Measure the spool instead of disabling the daily-byte quota for chunked clients.
    current = file.file.tell()
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(current)
    return int(size)


def _sha256_stream(stream: BinaryIO) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


async def _persist_reference_metadata(
    session: SessionDep,
    reference: object,
    *,
    size_bytes: int,
    probe: MediaProbe,
) -> None:
    # Byte size is measured on every upload. Never replace already verified media
    # metadata with an unavailable/failed replay probe: a transient ffprobe issue
    # must not turn a trusted reference back into an unverified billing source.
    setattr(reference, "size_bytes", size_bytes)
    previously_ready = getattr(reference, "probe_status", None) == "ready"
    if probe.status == "ready" or not previously_ready:
        setattr(reference, "duration_ms", probe.duration_ms)
        setattr(reference, "width", probe.width)
        setattr(reference, "height", probe.height)
        setattr(reference, "container", probe.container)
        setattr(reference, "video_codec", probe.video_codec)
        setattr(reference, "audio_codec", probe.audio_codec)
        setattr(reference, "probe_status", probe.status)
    await session.commit()


def _metadata_view(reference: object) -> dict[str, object | None]:
    duration_ms = getattr(reference, "duration_ms", None)
    duration_seconds = None
    if isinstance(duration_ms, int) and duration_ms > 0:
        duration_seconds = max(1, (duration_ms + 999) // 1000)
    return {
        "probe_status": getattr(reference, "probe_status", None),
        "duration_ms": duration_ms,
        "duration_seconds": duration_seconds,
        "width": getattr(reference, "width", None),
        "height": getattr(reference, "height", None),
        "container": getattr(reference, "container", None),
        "video_codec": getattr(reference, "video_codec", None),
        "audio_codec": getattr(reference, "audio_codec", None),
    }


@router.post("/kie", status_code=status.HTTP_201_CREATED)
async def upload_to_kie(
    user: CurrentUserDep,
    redis: RedisDep,
    session: SessionDep,
    file: UploadFile = File(...),
) -> dict[str, object]:
    content_type = (file.content_type or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_MEDIA_PREFIXES):
        raise HTTPException(status_code=415, detail="Only image, video and audio files are allowed")

    size_bytes = _upload_size(file)
    if size_bytes > settings.kie_upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    await AbuseProtectionService.upload_rate_and_bytes(
        redis,
        user_id=user.id,
        size_bytes=size_bytes,
    )

    filename = file.filename or "upload"
    kind = content_type.split("/", 1)[0]
    file_hash = await asyncio.to_thread(_sha256_stream, file.file)
    probe = await asyncio.to_thread(probe_media_stream, file.file, filename)

    existing = await ReferenceService.get_by_hash(
        session,
        user_id=user.id,
        kind=kind,
        file_hash=file_hash,
    )
    if existing is not None:
        reference, _ = await ReferenceService.register(
            session,
            user_id=user.id,
            source_url=existing.source_url,
            kind=kind,
            original_filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            source="mini_app_upload",
        )
        await _persist_reference_metadata(
            session,
            reference,
            size_bytes=size_bytes,
            probe=probe,
        )
        return {
            "url": reference.source_url,
            "name": reference.original_filename or filename,
            "mime_type": reference.content_type or content_type,
            "size": size_bytes,
            "replayed": True,
            "reference": ReferenceService.public_view(reference),
            **_metadata_view(reference),
        }

    client = KieUploadClient(settings.kie_api_key, settings.kie_upload_base_url)
    try:
        await file.seek(0)
        uploaded = await client.upload_stream(
            file_name=filename,
            content_type=content_type,
            stream=file.file,
        )
    except KieProviderError as exc:
        raise HTTPException(status_code=502, detail="Media upload failed") from exc
    finally:
        await client.aclose()

    reference, replayed = await ReferenceService.register(
        session,
        user_id=user.id,
        source_url=uploaded.url,
        kind=kind,
        original_filename=filename,
        content_type=uploaded.mime_type or content_type,
        file_hash=file_hash,
        source="mini_app_upload",
    )
    await _persist_reference_metadata(
        session,
        reference,
        size_bytes=size_bytes,
        probe=probe,
    )

    return {
        "url": reference.source_url,
        "name": uploaded.name,
        "mime_type": uploaded.mime_type,
        "size": uploaded.size,
        "replayed": replayed,
        "reference": ReferenceService.public_view(reference),
        **_metadata_view(reference),
    }
