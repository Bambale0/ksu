from __future__ import annotations

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Generation
from app.services.generation_action_contexts import (
    ActionContextDisabledError,
    ActionContextError,
    ActionContextExpiredError,
    ActionContextNotFoundError,
    create_action_context,
    get_action_context,
)
from app.core.config import settings

router = APIRouter(tags=["generation-action-contexts"])


class CreateActionContextRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)


async def _owned_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Generation:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


def _http_error(exc: ActionContextError) -> HTTPException:
    if isinstance(exc, (ActionContextDisabledError, ActionContextNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ActionContextExpiredError):
        return HTTPException(status_code=410, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


def _mini_app_url(context_id: uuid.UUID) -> str:
    base = settings.public_base_url.rstrip("/")
    query = urlencode({"route": "generation-action", "action_context_id": str(context_id)})
    return f"{base}/mini-app/?{query}"


def _context_meta(context) -> dict[str, object]:
    payload = dict(context.payload_json or {})
    payload.update(
        {
            "action_context_id": str(context.id),
            "action_context_status": context.status,
            "action_context_expires_at": context.expires_at.isoformat()
            if context.expires_at
            else None,
            "target_mode": context.target_mode,
            "target_model_id": context.target_model_id,
        }
    )
    return payload


@router.post("/generations/{generation_id}/action-contexts")
async def create_context(
    generation_id: uuid.UUID,
    payload: CreateActionContextRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    try:
        context = await create_action_context(
            session,
            user_id=user.id,
            generation=generation,
            action=payload.action,
        )
    except ActionContextError as exc:
        raise _http_error(exc) from exc
    await session.commit()
    return {
        "id": str(context.id),
        "action_context_id": str(context.id),
        "action": context.action,
        "source_generation_id": str(context.source_generation_id),
        # Mini App scenario route (query-based routing, same as open_app_url).
        "route": f"/mini-app/?route=generation-action&action_context_id={context.id}",
        "target_mode": context.target_mode,
        "target_model_id": context.target_model_id,
        "expires_at": context.expires_at.isoformat(),
        "open_app_url": _mini_app_url(context.id),
        "status": context.status,
    }


@router.get("/generation-action-contexts/{context_id}")
async def read_context(
    context_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        context = await get_action_context(session, context_id, user.id)
    except ActionContextError as exc:
        raise _http_error(exc) from exc
    await session.commit()
    return _context_meta(context)


@router.get("/action-context/{context_id}")
async def read_context_alias(
    context_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    """Contract alias: GET /api/v1/action-context/{id}."""
    return await read_context(context_id, user, session)