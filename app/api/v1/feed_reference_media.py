from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUserDep, SessionDep
from app.services.feed import FeedNotFoundError, FeedService
from app.services.reference_previews import ReferencePreviewService
from app.services.reference_static import ReferenceStaticStorage

router = APIRouter(prefix="/feed", tags=["feed"])


def _cache_headers(*, immutable: bool) -> dict[str, str]:
    if immutable:
        return {
            "Cache-Control": "public, max-age=31536000, s-maxage=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        }
    return {
        "Cache-Control": "public, max-age=86400, s-maxage=86400",
        "X-Content-Type-Options": "nosniff",
    }


async def _visible_reference_image(
    session: SessionDep,
    *,
    generation_id: uuid.UUID,
    index: int,
    surface: str,
) -> tuple[str, Path]:
    try:
        generation = await FeedService.assert_surface_visible(
            session,
            generation_id,
            surface=surface,
        )
    except (FeedNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found") from exc

    if generation.source_feed_gen_id is not None or not generation.feed_references_visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")

    images, _videos = FeedService._references(generation)
    if index < 0 or index >= len(images):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    source_url = images[index]
    source = ReferenceStaticStorage.path_for_url(source_url)
    if source is None or not source.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    return source_url, source


@router.get("/reference-image/{generation_id}/{index}/thumbnail")
async def feed_reference_image_thumbnail(
    generation_id: uuid.UUID,
    index: int,
    _user: CurrentUserDep,
    session: SessionDep,
    surface: str = Query(default="feed", pattern="^(feed|profile)$"),
) -> FileResponse:
    source_url, _source = await _visible_reference_image(
        session,
        generation_id=generation_id,
        index=index,
        surface=surface,
    )
    thumbnail = ReferencePreviewService.thumbnail_path(source_url)
    if thumbnail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference preview unavailable")
    return FileResponse(
        thumbnail,
        media_type="image/webp",
        headers=_cache_headers(immutable=True),
    )


@router.get("/reference-image/{generation_id}/{index}/full")
async def feed_reference_image_full(
    generation_id: uuid.UUID,
    index: int,
    _user: CurrentUserDep,
    session: SessionDep,
    surface: str = Query(default="feed", pattern="^(feed|profile)$"),
) -> FileResponse:
    _source_url, source = await _visible_reference_image(
        session,
        generation_id=generation_id,
        index=index,
        surface=surface,
    )
    return FileResponse(
        source,
        headers=_cache_headers(immutable=False),
    )
