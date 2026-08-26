from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, SessionDep
from app.db.admin_content_models import GenerationModerationState
from app.services.feed import (
    FeedDerivativePublicationError,
    FeedMediaUnavailableError,
    FeedNotFoundError,
    FeedPublicationError,
    FeedService,
)

router = APIRouter(tags=["feed"])


class AdultPublishRequest(BaseModel):
    prompt_visible: bool = False
    references_visible: bool = False


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FeedNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (FeedDerivativePublicationError, FeedMediaUnavailableError, FeedPublicationError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail="Feed operation failed")


@router.post("/feed/{generation_id}/publish-adult")
async def publish_adult_feed_generation(
    generation_id: uuid.UUID,
    payload: AdultPublishRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    """Queue a creator-declared 18+ publication for admin moderation.

    The media is localized by the ordinary durable feed publication contract
    first, but the generation stays absent from feed/profile surfaces until an
    admin chooses ``visible`` or ``blurred``.
    """

    try:
        generation = await FeedService.share_to_feed(
            session,
            generation_id=generation_id,
            owner_user_id=user.id,
            publication_scope="feed",
            prompt_visible=payload.prompt_visible,
            references_visible=payload.references_visible,
            adult_content=True,
        )
        moderation = await session.get(GenerationModerationState, generation.id)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise _http_error(exc) from exc

    state = moderation.state if moderation is not None else "pending"
    return {
        "id": str(generation.id),
        "publication_scope": generation.publication_scope,
        "adult_content": True,
        "moderation_state": state,
        "pending_moderation": state == "pending",
        "is_public_feed": bool(generation.is_public_feed),
        "is_profile_visible": bool(generation.is_profile_visible),
    }
