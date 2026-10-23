from __future__ import annotations

import asyncio
import hashlib
from functools import partial
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.core.config import settings
from app.services.abuse_protection import AbuseProtectionService
from app.services.media_probe import MediaProbe, probe_media_stream
from app.services.reference_static import ReferenceStaticStorage, ReferenceStaticStorageError
from app.services.references import ReferenceService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MEDIA_PREFIXES = ("image/", "video/", "audio/")
OCTET_STREAM_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
FALLBACK_MEDIA_TYPES_BY_EXTENSION = {
    ".aac": "audio/aac",
    ".aif": "audio/aiff",
    ".aiff": "audio/aiff",
    ".avi": "video/x-msvideo",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".flac": "audio/flac",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".m4a": "audio/mp4",
    ".m4v": "video/x-m4v",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".ogg": "audio/ogg",
    ".ogv": "video/ogg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".wav": "audio/wav",
    ".webm": "video/webm",
    ".webp": "image/webp",
}


def _upload_size(file: UploadFile) -> int:
    current = file.file.tell()
    try:
        file.file.seek(0, 2)
        return int(file.file.tell())
    finally:
        file.file.seek(current)


def _fallback_content_type(filename: str | None) -> str | None:
    suffix = Path(filename or "").suffix.lower()
    return FALLBACK_MEDIA_TYPES_BY_EXTENSION.get(suffix)


def _upload_content_type(file: UploadFile) -> str:
    declared = ReferenceStaticStorage.normalize_content_type(file.content_type)
    if ReferenceStaticStorage.supports_content_type(declared):
        return declared
    if declared in OCTET_STREAM_TYPES:
        fallback = _fallback_content_type(file.filename)
        if fallback and ReferenceStaticStorage.supports_content_type(fallback):
            return fallback
    return declared or "application/octet-stream"


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


def _probed_content_type(content_type: str, probe: MediaProbe) -> str:
    # Shared containers may arrive with a video MIME even when they contain
    # only sound. Use verified streams and container metadata before choosing
    # the durable storage path, extension and saved-reference kind.
    if (
        not content_type.startswith(("audio/", "video/"))
        or probe.status != "ready"
        or probe.has_video is not False
        or not probe.audio_codec
    ):
        return content_type
    containers = set((probe.container or "").split(","))
    # MOV and MP4 share a demuxer name. Only verified MP4/M4A brands justify
    # changing the MIME/extension; this does not transcode QuickTime bytes.
    if containers & {"mov", "mp4", "m4a"}:
        if probe.container_brand in {"isom", "iso2", "mp41", "mp42", "M4A", "M4B"}:
            return "audio/mp4"
        return content_type
    for formats, audio_type in (
        ({"ogg"}, "audio/ogg"),
        ({"mp3"}, "audio/mpeg"),
        ({"wav"}, "audio/wav"),
        ({"aac"}, "audio/aac"),
        ({"flac"}, "audio/flac"),
        ({"aiff"}, "audio/aiff"),
    ):
        if containers & formats:
            return audio_type
    return content_type


async def _persist_reference_metadata(
    session: SessionDep,
    reference: object,
    *,
    size_bytes: int,
    probe: MediaProbe,
) -> None:
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
    await session.refresh(reference)


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
    """Persist a reusable reference under ROXY ownership.

    The legacy route name is kept for Mini App compatibility. The upload is no
    longer stored as a temporary Kie URL. Kie transport happens just in time in
    the generation worker so saved references remain reusable indefinitely.
    """

    content_type = _upload_content_type(file)
    if not ReferenceStaticStorage.supports_content_type(content_type):
        raise HTTPException(status_code=415, detail="Only supported image, video and audio files are allowed")

    size_bytes = _upload_size(file)
    if size_bytes > settings.kie_upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    await AbuseProtectionService.upload_rate_and_bytes(
        redis,
        user_id=user.id,
        size_bytes=size_bytes,
    )

    filename = file.filename or "upload"
    file_hash = await asyncio.to_thread(_sha256_stream, file.file)
    probe = await asyncio.to_thread(probe_media_stream, file.file, filename)
    content_type = _probed_content_type(content_type, probe)
    kind = content_type.split("/", 1)[0]

    existing = await ReferenceService.get_by_hash(
        session,
        user_id=user.id,
        kind=kind,
        file_hash=file_hash,
    )
    if existing is not None and ReferenceStaticStorage.local_url_exists(existing.source_url):
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

    try:
        local_url, _path, stored_size = await asyncio.to_thread(
            partial(
                ReferenceStaticStorage.persist_stream,
                file.file,
                user_id=user.id,
                kind=kind,
                file_hash=file_hash,
                filename=filename,
                content_type=content_type,
                expected_size=size_bytes,
            )
        )
    except ReferenceStaticStorageError as exc:
        raise HTTPException(status_code=500, detail="Reference storage failed") from exc

    reference, replayed = await ReferenceService.register(
        session,
        user_id=user.id,
        source_url=local_url,
        kind=kind,
        original_filename=filename,
        content_type=content_type,
        file_hash=file_hash,
        source="mini_app_upload",
    )
    await _persist_reference_metadata(
        session,
        reference,
        size_bytes=stored_size,
        probe=probe,
    )

    return {
        "url": reference.source_url,
        "name": reference.original_filename or filename,
        "mime_type": reference.content_type or content_type,
        "size": stored_size,
        "replayed": replayed,
        "reference": ReferenceService.public_view(reference),
        **_metadata_view(reference),
    }


@router.post('/template-audio', status_code=status.HTTP_201_CREATED)
async def upload_template_audio(
    user: CurrentUserDep,
    redis: RedisDep,
    session: SessionDep,
    file: UploadFile = File(...),
) -> dict[str, object]:
    """Upload verified, product-owned audio without touching personal memory."""
    import uuid

    from app.api.v1.trends import _inline_admin
    from app.db.reference_models import TemplateAudioReference
    from app.services.admin_policy import AdminPolicyError

    try:
        await _inline_admin(session, user_id=user.id)
    except AdminPolicyError as exc:
        raise HTTPException(status_code=403, detail="Admin permission required") from exc
    content_type = _upload_content_type(file)
    if not content_type.startswith('audio/') or not ReferenceStaticStorage.supports_content_type(content_type):
        raise HTTPException(status_code=415, detail='Only supported audio files are allowed')
    size_bytes = _upload_size(file)
    if size_bytes > settings.kie_upload_max_bytes:
        raise HTTPException(status_code=413, detail='File is too large')
    await AbuseProtectionService.upload_rate_and_bytes(redis, user_id=user.id, size_bytes=size_bytes)
    filename = file.filename or 'audio'
    probe = await asyncio.to_thread(probe_media_stream, file.file, filename)
    if probe.status != 'ready' or not probe.duration_ms or probe.duration_ms <= 0 or not probe.audio_codec or probe.video_codec:
        raise HTTPException(status_code=422, detail='Audio duration could not be verified')
    file_hash = await asyncio.to_thread(_sha256_stream, file.file)
    reference_id = uuid.uuid4()
    # A fresh asset namespace prevents personal re-uploads or later retries from
    # sharing bytes with an asset being disposed. Attribution is stored separately.
    try:
        url, _path, stored_size = await asyncio.to_thread(partial(
            ReferenceStaticStorage.persist_stream, file.file, user_id=reference_id,
            kind='audio', file_hash=file_hash, filename=filename,
            content_type=content_type, expected_size=size_bytes,
        ))
    except ReferenceStaticStorageError as exc:
        raise HTTPException(status_code=500, detail='Reference storage failed') from exc
    row = TemplateAudioReference(
        id=reference_id, source_url=url, uploaded_by=user.id, status='ready',
        original_filename=filename[:255], content_type=content_type,
        size_bytes=stored_size, duration_ms=probe.duration_ms, probe_status='ready',
    )
    session.add(row)
    await session.commit()
    return {
        'url': url, 'name': filename, 'mime_type': content_type, 'size': stored_size,
        'probe_status': 'ready', 'duration_ms': probe.duration_ms,
        'reference': {'id': str(row.id), 'kind': 'audio', 'url': url},
    }
