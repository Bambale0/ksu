from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep
from app.core.config import settings
from app.providers.kie import KieProviderError
from app.providers.kie_uploads import KieUploadClient

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MEDIA_PREFIXES = ("image/", "video/", "audio/")


@router.post("/kie", status_code=status.HTTP_201_CREATED)
async def upload_to_kie(
    _user: CurrentUserDep,
    file: UploadFile = File(...),
) -> dict[str, object]:
    content_type = (file.content_type or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_MEDIA_PREFIXES):
        raise HTTPException(status_code=415, detail="Only image, video and audio files are allowed")

    if file.size is not None and file.size > settings.kie_upload_max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")

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
