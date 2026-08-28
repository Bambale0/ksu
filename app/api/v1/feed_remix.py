from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.feed import FeedError, FeedNotFoundError
from app.services.feed_remix import FeedRemixReferenceError, FeedRemixService
from app.services.model_catalog import InvalidModelParametersError, UnknownModelError
from app.services.wallet import InsufficientBalanceError

router = APIRouter(tags=["feed"])


class RemixCompositionRequest(BaseModel):
    surface: Literal["feed", "profile"] = "feed"
    prompt: str | None = Field(default=None, max_length=8000)
    reference_ids: list[uuid.UUID] = Field(default_factory=list, max_length=36)
    confirm_own_references: bool = False


def _remix_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FeedNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, InsufficientBalanceError):
        return HTTPException(status_code=409, detail="Insufficient credits")
    if isinstance(
        exc,
        (FeedRemixReferenceError, FeedError, InvalidModelParametersError, UnknownModelError, ValueError),
    ):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Feed repeat failed")


@router.get("/feed/{generation_id}/remix/prepare")
async def prepare_feed_remix(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    surface: Literal["feed", "profile"] = Query(default="feed"),
) -> dict[str, object]:
    try:
        return await FeedRemixService.prepare(
            session,
            source_generation_id=generation_id,
            viewer_user_id=user.id,
            surface=surface,
        )
    except Exception as exc:
        raise _remix_error(exc) from exc


@router.post("/feed/{generation_id}/remix/quote")
async def quote_feed_remix(
    generation_id: uuid.UUID,
    payload: RemixCompositionRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        return await FeedRemixService.quote(
            session,
            source_generation_id=generation_id,
            remix_author_id=user.id,
            surface=payload.surface,
            prompt_override=payload.prompt,
            reference_ids=payload.reference_ids,
            confirm_own_references=payload.confirm_own_references,
        )
    except Exception as exc:
        raise _remix_error(exc) from exc


@router.post("/feed/{generation_id}/remix/launch", status_code=status.HTTP_202_ACCEPTED)
async def launch_feed_remix(
    generation_id: uuid.UUID,
    payload: RemixCompositionRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    try:
        generation = await FeedRemixService.launch(
            session,
            redis,
            source_generation_id=generation_id,
            remix_author_id=user.id,
            surface=payload.surface,
            prompt_override=payload.prompt,
            reference_ids=payload.reference_ids,
            confirm_own_references=payload.confirm_own_references,
        )
    except Exception as exc:
        raise _remix_error(exc) from exc
    return {
        "id": str(generation.id),
        "status": generation.status,
        "source_feed_gen_id": str(generation.source_feed_gen_id),
        "parent_generation_id": str(generation.parent_generation_id),
        "action_type": generation.action_type,
        "cost_rox": format(generation.cost_rox, ".2f"),
    }
