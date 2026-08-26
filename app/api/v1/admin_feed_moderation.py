from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.services.feed_adult_moderation import FeedAdultModerationService

router = APIRouter(prefix="/admin/feed-moderation", tags=["admin-feed-moderation"])
AdminSocialDep = Annotated[AdminContext, Depends(require_permission("social.moderate"))]


@router.get("")
async def list_feed_moderation_queue(
    context: AdminSocialDep,
    session: SessionDep,
    state: Literal["pending", "visible", "blurred", "removed"] | None = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    try:
        return await FeedAdultModerationService.list_admin_queue(
            session,
            admin=context.account,
            state=state,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
