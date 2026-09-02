from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.api.v1.generations import (
    CreateGenerationRequest,
    _recreate_payload_for_generation,
    create_generation,
    quote_generation,
)
from app.db.models import Generation
from app.services.feed_links import mini_app_deep_link
from app.services.private_repeat_links import (
    apply_repeat_reference_parameters,
    generation_id_from_repeat_token,
    public_repeat_descriptor,
    repeat_token,
    sanitize_repeat_recipe,
)

router = APIRouter(tags=["generation-repeat-links"])


class PrivateRepeatInputs(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


async def _resolved_repeat_recipe(token: str, session: SessionDep) -> dict[str, object]:
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


def _repeat_generation_request(
    recipe: dict[str, object],
    inputs: PrivateRepeatInputs,
) -> CreateGenerationRequest:
    try:
        merged = apply_repeat_reference_parameters(recipe, inputs.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CreateGenerationRequest(
        model_id=str(merged.get("model_id") or ""),
        prompt=str(merged.get("prompt") or ""),
        input_url=str(merged["input_url"]) if merged.get("input_url") else None,
        billing_seconds=(
            int(merged["billing_seconds"])
            if merged.get("billing_seconds") is not None
            else None
        ),
        parameters=dict(merged.get("parameters") or {}),
        quantity=1,
    )


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
    del user  # Authentication is required; source ownership and recipe stay private.
    recipe = await _resolved_repeat_recipe(token, session)
    return public_repeat_descriptor(recipe)


@router.post("/generation-repeat-links/{token}/quote")
async def quote_private_repeat(
    token: str,
    payload: PrivateRepeatInputs,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    recipe = await _resolved_repeat_recipe(token, session)
    request = _repeat_generation_request(recipe, payload)
    return await quote_generation(request, user, session)


@router.post("/generation-repeat-links/{token}/launch", status_code=202)
async def launch_private_repeat(
    token: str,
    payload: PrivateRepeatInputs,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | bool | None | int | list[str]]:
    recipe = await _resolved_repeat_recipe(token, session)
    request = _repeat_generation_request(recipe, payload)
    return await create_generation(request, user, session, redis)
