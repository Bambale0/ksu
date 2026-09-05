from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.api.deps import CurrentUserDep, SessionDep
from app.db.admin_content_models import GenerationModerationState
from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.services.local_media_storage import LocalMediaStorage, LocalMediaStorageError
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured

router = APIRouter(prefix="/media", tags=["media"])


def _owned_asset(asset_id: uuid.UUID, user_id: uuid.UUID, asset: MediaAsset | None) -> MediaAsset:
    if asset is None or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


def _ready_asset(asset: MediaAsset | None) -> MediaAsset:
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.status != "ready" or not asset.object_key or not asset.bucket:
        raise HTTPException(status_code=409, detail="Media asset is not ready")
    return asset


def _filename(asset: MediaAsset) -> str:
    suffix = ""
    if asset.object_key:
        match = re.search(r"(\.[A-Za-z0-9]{1,8})$", asset.object_key)
        suffix = match.group(1).lower() if match else ""
    return f"generation-{asset.generation_id}-{asset.ordinal + 1}{suffix}"


def _local_file_response(
    asset: MediaAsset,
    *,
    download: bool,
    public: bool = False,
) -> FileResponse:
    try:
        path = LocalMediaStorage.path_for_key(asset.object_key or "")
    except LocalMediaStorageError as exc:
        raise HTTPException(status_code=503, detail="Media storage is unavailable") from exc
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Media file is missing from server storage")
    headers = {
        "Cache-Control": (
            "public, max-age=31536000, immutable"
            if public
            else "private, max-age=60"
        )
    }
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{_filename(asset)}"'
    return FileResponse(
        path=path,
        media_type=asset.content_type or None,
        headers=headers,
    )


def _storage_response(
    asset: MediaAsset,
    *,
    download: bool,
    public: bool = False,
) -> Response:
    if LocalMediaStorage.is_local_bucket(asset.bucket):
        return _local_file_response(asset, download=download, public=public)
    if not ObjectStorage.configured():
        raise HTTPException(status_code=503, detail="Legacy media storage is unavailable")
    try:
        storage = ObjectStorage()
        url = storage.presign_get(
            key=asset.object_key or "",
            bucket=asset.bucket,
            download_filename=_filename(asset) if download else None,
        )
    except ObjectStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Legacy media storage is unavailable") from exc
    return RedirectResponse(url=url, status_code=307)


def _public_generation(
    generation: Generation | None,
    moderation: GenerationModerationState | None,
) -> Generation:
    if generation is None or generation.status != "succeeded":
        raise HTTPException(status_code=404, detail="Media asset not found")
    if moderation is not None and moderation.state == "removed":
        raise HTTPException(status_code=404, detail="Media asset not found")
    if generation.publication_scope == "feed":
        if not generation.is_public_feed or not generation.is_profile_visible or generation.is_adult_content:
            raise HTTPException(status_code=404, detail="Media asset not found")
        return generation
    if generation.publication_scope == "profile" and generation.is_profile_visible:
        return generation
    raise HTTPException(status_code=404, detail="Media asset not found")


@router.get("/{asset_id}")
async def get_media_asset(
    asset_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    asset = _owned_asset(asset_id, user.id, await session.get(MediaAsset, asset_id))
    return {
        "id": str(asset.id),
        "generation_id": str(asset.generation_id),
        "status": asset.status,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "ordinal": asset.ordinal,
        "download_url": f"/api/v1/media/{asset.id}/download" if asset.status == "ready" else None,
    }


@router.get("/{asset_id}/download")
async def download_media_asset(
    asset_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Response:
    asset = _ready_asset(_owned_asset(asset_id, user.id, await session.get(MediaAsset, asset_id)))
    return _storage_response(asset, download=True)


@router.get("/{asset_id}/signed/{expires}/{signature}")
async def signed_media_asset(
    asset_id: uuid.UUID,
    expires: int,
    signature: str,
    session: SessionDep,
) -> Response:
    asset = _ready_asset(await session.get(MediaAsset, asset_id))
    if not LocalMediaStorage.is_local_bucket(asset.bucket):
        raise HTTPException(status_code=404, detail="Media asset not found")
    try:
        valid = LocalMediaStorage.verify_view_signature(
            asset_id=asset.id,
            key=asset.object_key or "",
            expires=expires,
            signature=signature,
        )
    except LocalMediaStorageError as exc:
        raise HTTPException(status_code=503, detail="Media storage is unavailable") from exc
    if not valid:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return _storage_response(asset, download=False)


@router.get("/{asset_id}/public")
@router.get("/{asset_id}/public/{filename}")
async def public_media_asset(
    asset_id: uuid.UUID,
    session: SessionDep,
    filename: str | None = None,
) -> Response:
    asset = _ready_asset(await session.get(MediaAsset, asset_id))
    generation = await session.get(Generation, asset.generation_id)
    moderation = await session.get(GenerationModerationState, asset.generation_id)
    _public_generation(generation, moderation)
    return _storage_response(asset, download=False, public=True)
