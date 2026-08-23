from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.models import Generation
from app.services.generation_action_contexts import (
    ActionContextError,
    build_action_context_payload,
    context_generation,
    mark_action_context_executed,
)
from app.services.generation_actions import DERIVATIVE_ACTIONS, GenerationActionService
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog, UnknownModelError
from app.services.music_generation import MUSIC_MODEL_ID, MusicGenerationError, MusicGenerationService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generation-actions"])


class DeriveGenerationRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=8000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    billing_seconds: int | None = Field(default=None, ge=1, le=600)
    edit_kind: str | None = Field(default=None, max_length=32)
    action_context_id: uuid.UUID | None = Field(default=None)


def _amount(value: object) -> str:
    return format(Decimal(str(value)), ".2f")


async def _owned_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Generation:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


@router.get("/{generation_id}/actions")
async def generation_actions(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    return {
        "generation": context_generation(generation),
        "actions": [item.public_dict() for item in GenerationActionService.available_actions(generation)],
    }


@router.get("/{generation_id}/action-context")
async def generation_action_context(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    action: str = Query(min_length=1, max_length=32),
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    try:
        return build_action_context_payload(generation, action)
    except ActionContextError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{generation_id}/actions/{action}", status_code=202)
async def derive_generation(
    generation_id: uuid.UUID,
    action: str,
    payload: DeriveGenerationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    parent = await _owned_generation(generation_id, user, session)
    if action not in DERIVATIVE_ACTIONS or not GenerationActionService.action_allowed(parent, action):
        raise HTTPException(status_code=409, detail="Action is not available for this generation")

    candidate_ids = {
        str(item.get("id") or "")
        for item in GenerationActionService.public_candidates(parent, action)
        if item.get("id")
    }
    if payload.model_id not in candidate_ids:
        raise HTTPException(
            status_code=422,
            detail="Selected model is not compatible with this generation action",
        )

    canonical = GenerationActionService.canonical_action(action)
    prompt = payload.prompt.strip()
    parameters = dict(payload.parameters or {})
    input_url: str | None = None

    async def _mark_context_executed() -> None:
        if not payload.action_context_id:
            return
        changed = await mark_action_context_executed(
            session, payload.action_context_id, user.id
        )
        if changed:
            await session.commit()

    if canonical in {"remix", "edit", "animate"}:
        input_url = GenerationActionService.result_url(parent)
        if not input_url:
            raise HTTPException(status_code=409, detail="Parent generation has no reusable result")
        if not prompt:
            raise HTTPException(status_code=422, detail="Describe what should change")
        if canonical == "edit":
            prompt = GenerationActionService.edit_prompt(prompt, payload.edit_kind)
    elif canonical == "repeat":
        if parent.action_type == "trend":
            raise HTTPException(status_code=409, detail="Trend prompt cannot be reconstructed")
        if action == "new_prompt" and not prompt:
            raise HTTPException(status_code=422, detail="Enter a new prompt")
        if not prompt:
            prompt = parent.prompt

        if MusicGenerationService.is_music_model(payload.model_id):
            base = GenerationActionService.reusable_parameters(parent, MUSIC_MODEL_ID)
            base.update(parameters)
            try:
                generation = await MusicGenerationService.create(
                    session,
                    redis,
                    user_id=user.id,
                    prompt=prompt,
                    parameters=base,
                )
            except (MusicGenerationError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except InsufficientBalanceError as exc:
                raise HTTPException(status_code=409, detail="Insufficient credits") from exc
            generation.parent_generation_id = parent.id
            generation.action_type = "repeat"
            await session.commit()
            await _mark_context_executed()
            return {
                "id": str(generation.id),
                "status": generation.status,
                "parent_generation_id": str(parent.id),
                "action_type": generation.action_type,
                "cost_rox": _amount(generation.cost_rox),
            }

        try:
            target = ModelCatalog.get(payload.model_id)
        except UnknownModelError as exc:
            raise HTTPException(status_code=422, detail="Unknown generation model") from exc
        base = GenerationActionService.reusable_parameters(parent, target.id)
        base.update(parameters)
        parameters, input_url = GenerationActionService.adapt_references(parent, target, base)

    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            model_id=payload.model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=payload.billing_seconds,
            parent_generation_id=parent.id,
            action_type=canonical,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient credits") from exc

    await _mark_context_executed()

    return {
        "id": str(generation.id),
        "status": generation.status,
        "parent_generation_id": str(parent.id),
        "action_type": generation.action_type,
        "cost_rox": _amount(generation.cost_rox),
    }
