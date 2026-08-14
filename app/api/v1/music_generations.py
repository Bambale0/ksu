from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.api.v1 import generations as base_generations
from app.db.models import Generation
from app.services.credits import InternalCreditService
from app.services.music_generation import MUSIC_MODEL_ID, MusicGenerationError, MusicGenerationService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generations", "music"])


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _is_music_view(view: dict[str, object]) -> bool:
    model = view.get("model")
    return isinstance(model, dict) and str(model.get("id") or "") == MUSIC_MODEL_ID


def _enrich_music_view(
    view: dict[str, object],
    *,
    generation: Generation | None = None,
) -> dict[str, object]:
    if not _is_music_view(view):
        return view
    view["model"] = {
        "id": MUSIC_MODEL_ID,
        "title": "Suno V5.5 · Music",
        "family": "suno",
        "operation": "text_to_music",
        "media_type": "audio",
    }
    if generation is not None:
        params = dict(generation.parameters or {})
        view["settings"] = MusicGenerationService.public_settings(params)
        tracks = params.get("_music_tracks")
        view["music_tracks"] = tracks if isinstance(tracks, list) else []
    return view


@router.get("/models")
async def generation_models() -> dict[str, object]:
    payload = await base_generations.generation_models()
    models = list(payload.get("models") or [])
    if not any(str(item.get("id") or "") == MUSIC_MODEL_ID for item in models if isinstance(item, dict)):
        models.append(MusicGenerationService.public_model())
    return {**payload, "models": models}


@router.post("/quote")
async def quote_generation(
    payload: base_generations.CreateGenerationRequest,
    session: SessionDep,
) -> dict[str, Any]:
    if not MusicGenerationService.is_music_model(payload.model_id):
        return await base_generations.quote_generation(payload, session)
    try:
        _clean, cost = MusicGenerationService.prepare(payload.parameters, payload.prompt)
    except MusicGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "model_id": MUSIC_MODEL_ID,
        "price_mode": "flat",
        "unit_price_credits": _amount(cost),
        "unit_price_rox": _amount(cost),
        "unit_price_rub": _amount(InternalCreditService.rubles_for(cost)),
        "billing_seconds": None,
        "cost_credits": _amount(cost),
        "cost_rox": _amount(cost),
        "cost_rub": _amount(InternalCreditService.rubles_for(cost)),
        "internal_credit_rub": _amount(InternalCreditService.rub_per_credit()),
    }


@router.get("")
async def list_generations(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=50),
    before: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
) -> dict[str, object]:
    payload = await base_generations.list_generations(
        user,
        session,
        limit=limit,
        before=before,
        status_filter=status_filter,
    )
    items = payload.get("items")
    if isinstance(items, list):
        payload["items"] = [
            _enrich_music_view(item) if isinstance(item, dict) else item
            for item in items
        ]
    return payload


@router.get("/{generation_id}")
async def get_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await session.get(Generation, generation_id)
    payload = await base_generations.get_generation(generation_id, user, session)
    return _enrich_music_view(payload, generation=generation)


@router.get("/{generation_id}/recreate")
async def recreate_generation_payload(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if str((generation.parameters or {}).get("_model_id") or "") != MUSIC_MODEL_ID:
        return await base_generations.recreate_generation_payload(generation_id, user, session)
    return {
        "model_id": MUSIC_MODEL_ID,
        "prompt": generation.prompt,
        "input_url": None,
        "billing_seconds": None,
        "parameters": MusicGenerationService.reusable_parameters(generation.parameters or {}),
    }


@router.post("", status_code=202)
async def create_generation(
    payload: base_generations.CreateGenerationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | None]:
    if not MusicGenerationService.is_music_model(payload.model_id):
        return await base_generations.create_generation(payload, user, session, redis)
    try:
        generation = await MusicGenerationService.create(
            session,
            redis,
            user_id=user.id,
            prompt=payload.prompt,
            parameters=payload.parameters,
        )
    except MusicGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient credits") from exc
    return {
        "id": str(generation.id),
        "status": generation.status,
        "cost_credits": _amount(generation.cost_rox),
        "cost_rox": _amount(generation.cost_rox),
        "cost_rub": _amount(InternalCreditService.rubles_for(generation.cost_rox)),
        "result_url": generation.result_url,
    }
