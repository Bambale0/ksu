from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.history_models import GenerationHistoryState
from app.db.models import Generation
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import (
    InvalidModelParametersError,
    ModelCatalog,
    UnknownModelError,
)
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generations"])


class CreateGenerationRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=8000)
    input_url: str | None = Field(default=None, max_length=4000)
    billing_seconds: int | None = Field(default=None, ge=1, le=600)
    parameters: dict[str, Any] = Field(default_factory=dict)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _model_view(generation: Generation) -> dict[str, str | None]:
    model_id = str((generation.parameters or {}).get("_model_id") or "")
    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return {
            "id": model_id or None,
            "title": model_id or "Unknown model",
            "family": None,
            "operation": generation.kind,
            "media_type": None,
        }
    return {
        "id": spec.id,
        "title": spec.title,
        "family": spec.family,
        "operation": spec.operation,
        "media_type": spec.media_type,
    }


def _result_urls(generation: Generation) -> list[str]:
    raw = (generation.parameters or {}).get("_result_urls")
    values = [str(item) for item in raw] if isinstance(raw, list) else []
    if generation.result_url and generation.result_url not in values:
        values.insert(0, generation.result_url)
    return values


def _public_settings(generation: Generation) -> dict[str, Any]:
    params = dict(generation.parameters or {})
    model_id = str(params.get("_model_id") or "")
    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return {}
    allowed = set(spec.known_fields)
    return {
        key: value
        for key, value in params.items()
        if key in allowed and not key.startswith("_") and key != "prompt"
    }


def _generation_view(generation: Generation, *, hidden: bool = False) -> dict[str, object]:
    cost = Decimal(generation.cost_rox)
    params = generation.parameters or {}
    return {
        "id": str(generation.id),
        "status": generation.status,
        "prompt": generation.prompt,
        "model": _model_view(generation),
        "settings": _public_settings(generation),
        "cost_credits": _amount(cost),
        "cost_rub": _amount(InternalCreditService.rubles_for(cost)),
        "billing_seconds": params.get("_billing_seconds"),
        "result_url": generation.result_url,
        "result_urls": _result_urls(generation),
        "error": generation.error,
        "hidden_from_history": hidden,
        "created_at": generation.created_at.isoformat(),
        "updated_at": generation.updated_at.isoformat(),
    }


async def _owned_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Generation:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


@router.get("/models")
async def generation_models() -> dict[str, object]:
    models: list[dict[str, Any]] = []
    for item in ModelCatalog.list():
        enriched = dict(item)
        unit_credits = enriched.get("price_rox")
        if unit_credits is not None:
            enriched["price_credits"] = _amount(unit_credits)
            enriched["price_rub"] = _amount(InternalCreditService.rubles_for(str(unit_credits)))
        enriched["ui_schema"] = build_public_model_ui_schema(enriched)
        models.append(enriched)
    return {
        "schema_version": 1,
        "internal_credit_rub": _amount(InternalCreditService.rub_per_credit()),
        "models": models,
    }


@router.post("/quote")
async def quote_generation(
    payload: CreateGenerationRequest,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        spec, _clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            session,
            model_id=payload.model_id,
            prompt=payload.prompt,
            input_url=payload.input_url,
            parameters=payload.parameters,
            billing_seconds=payload.billing_seconds,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "model_id": spec.id,
        "price_mode": spec.price_mode,
        "unit_price_credits": _amount(unit_price),
        "unit_price_rox": _amount(unit_price),
        "unit_price_rub": _amount(InternalCreditService.rubles_for(unit_price)),
        "billing_seconds": seconds,
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
    statement = (
        select(Generation)
        .outerjoin(
            GenerationHistoryState,
            and_(
                GenerationHistoryState.generation_id == Generation.id,
                GenerationHistoryState.user_id == user.id,
            ),
        )
        .where(
            Generation.user_id == user.id,
            or_(
                GenerationHistoryState.generation_id.is_(None),
                GenerationHistoryState.hidden_at.is_(None),
            ),
        )
    )
    if status_filter:
        statement = statement.where(Generation.status == status_filter)

    if before is not None:
        anchor = await session.get(Generation, before)
        if anchor is None or anchor.user_id != user.id:
            raise HTTPException(status_code=404, detail="History cursor not found")
        statement = statement.where(
            or_(
                Generation.created_at < anchor.created_at,
                and_(Generation.created_at == anchor.created_at, Generation.id < anchor.id),
            )
        )

    rows = list(
        (
            await session.scalars(
                statement.order_by(Generation.created_at.desc(), Generation.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [_generation_view(row) for row in page],
        "has_more": has_more,
        "next_before": str(page[-1].id) if has_more and page else None,
    }


@router.get("/{generation_id}")
async def get_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    history_state = await session.get(GenerationHistoryState, generation.id)
    hidden = bool(history_state and history_state.user_id == user.id and history_state.hidden_at)
    return _generation_view(generation, hidden=hidden)


@router.get("/{generation_id}/recreate")
async def recreate_generation_payload(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)

    params = dict(generation.parameters or {})
    model_id = str(params.get("_model_id") or "")
    if not model_id:
        raise HTTPException(status_code=409, detail="Generation has no reusable model")
    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError as exc:
        raise HTTPException(status_code=409, detail="Generation model is no longer available") from exc

    allowed = set(spec.known_fields)
    clean = {
        key: value
        for key, value in params.items()
        if not key.startswith("_") and key in allowed and key != "prompt"
    }
    return {
        "model_id": model_id,
        "prompt": generation.prompt,
        "input_url": generation.input_url,
        "billing_seconds": params.get("_billing_seconds"),
        "parameters": clean,
    }


@router.delete("/{generation_id}/history")
async def hide_generation_from_history(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, bool]:
    generation = await _owned_generation(generation_id, user, session)
    state = await session.get(GenerationHistoryState, generation.id)
    if state is None:
        state = GenerationHistoryState(generation_id=generation.id, user_id=user.id)
        session.add(state)
    elif state.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    state.hidden_at = datetime.now(timezone.utc)
    await session.commit()
    return {"hidden": True}


@router.post("/{generation_id}/history/restore")
async def restore_generation_to_history(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, bool]:
    generation = await _owned_generation(generation_id, user, session)
    state = await session.get(GenerationHistoryState, generation.id)
    if state is not None:
        if state.user_id != user.id:
            raise HTTPException(status_code=404, detail="Generation not found")
        state.hidden_at = None
        await session.commit()
    return {"hidden": False}


@router.post("", status_code=202)
async def create_generation(
    payload: CreateGenerationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | None]:
    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            model_id=payload.model_id,
            prompt=payload.prompt,
            input_url=payload.input_url,
            parameters=payload.parameters,
            billing_seconds=payload.billing_seconds,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
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
