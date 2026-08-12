from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, RedisDep
from app.core.config import settings
from app.providers.kie import KieProviderError
from app.providers.kie_uploads import KieUploadClient
from app.services.abuse_protection import AbuseProtectionService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MEDIA_PREFIXES = ("image/", "video/", "audio/")


@router.post("/kie", status_code=status.HTTP_201_CREATED)
async def upload_to_kie(
    user: CurrentUserDep,
    redis: RedisDep,
    file: UploadFile = File(...),
) -> dict[str, object]:
    content_type = (file.content_type or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_MEDIA_PREFIXES):
        raise HTTPException(status_code=415, detail="Only image, video and audio files are allowed")

    if file.size is None and settings.upload_daily_bytes_limit > 0:
        raise HTTPException(status_code=411, detail="Upload size is required")
    size_bytes = int(file.size or 0)
    if size_bytes > settings.kie_upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

    await AbuseProtectionService.upload_rate_and_bytes(
        redis,
        user_id=user.id,
        size_bytes=size_bytes,
    )

    filename = file.filename or "upload"
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

    return {
        "url": uploaded.url,
        "name": uploaded.name,
        "mime_type": uploaded.mime_type,
        "size": uploaded.size,
    }
