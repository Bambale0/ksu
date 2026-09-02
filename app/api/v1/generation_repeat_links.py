from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUserDep, SessionDep
from app.api.v1.generations import _recreate_payload_for_generation
from app.db.models import Generation
from app.services.feed_links import mini_app_deep_link
from app.services.private_repeat_links import (
    generation_id_from_repeat_token,
    repeat_token,
    sanitize_repeat_recipe,
)

router = APIRouter(tags=["generation-repeat-links"])


@router.post("/generations/{generation_id}/repeat-link")
async def create_private_repeat_link(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if generation.status != "succeeded":
        raise HTTPException(status_code=409, detail="Only a finished work can be repeated")

    # Validate that the generation still has a reusable model/recipe before a
    # link is handed to the creator. This does not publish or mutate the work.
    raw_recipe = _recreate_payload_for_generation(generation)
    recipe = sanitize_repeat_recipe(raw_recipe)
    if not recipe.get("model_id"):
        raise HTTPException(status_code=409, detail="Generation cannot be repeated")

    token = repeat_token(generation.id)
    payload = f"repeat_{token}"
    link = mini_app_deep_link(payload)
    if not link:
        raise HTTPException(status_code=503, detail="Telegram Mini App link is not configured")
    return {
        "link": link,
        "payload": payload,
        "private": True,
    }


@router.get("/generation-repeat-links/{token}")
async def resolve_private_repeat_link(
    token: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    del user  # Authentication is required; ownership of the source is not exposed.
    generation_id = generation_id_from_repeat_token(token)
    if generation_id is None:
        raise HTTPException(status_code=404, detail="Repeat link not found")

    generation = await session.get(Generation, generation_id)
    if generation is None or generation.status != "succeeded":
        raise HTTPException(status_code=404, detail="Repeat link not found")

    try:
        raw_recipe = _recreate_payload_for_generation(generation)
    except HTTPException as exc:
        # Do not reveal whether a private source exists or why it became unusable.
        raise HTTPException(status_code=404, detail="Repeat link not found") from exc
    return sanitize_repeat_recipe(raw_recipe)
