from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUserDep, SessionDep
from app.db.media_models import MediaAsset
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured

router = APIRouter(prefix="/media", tags=["media"])


def _owned_asset(asset_id: uuid.UUID, user_id: uuid.UUID, asset: MediaAsset | None) -> MediaAsset:
    if asset is None or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


def _filename(asset: MediaAsset) -> str:
    suffix = ""
    if asset.object_key:
        match = re.search(r"(\.[A-Za-z0-9]{1,8})$", asset.object_key)
        suffix = match.group(1).lower() if match else ""
    return f"generation-{asset.generation_id}-{asset.ordinal + 1}{suffix}"


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
) -> RedirectResponse:
    asset = _owned_asset(asset_id, user.id, await session.get(MediaAsset, asset_id))
    if asset.status != "ready" or not asset.object_key or not asset.bucket:
        raise HTTPException(status_code=409, detail="Media asset is not ready")
    try:
        storage = ObjectStorage()
        url = storage.presign_get(
            key=asset.object_key,
            bucket=asset.bucket,
            download_filename=_filename(asset),
        )
    except ObjectStorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Media storage is unavailable") from exc
    return RedirectResponse(url=url, status_code=307)
