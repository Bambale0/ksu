from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.generations import GenerationService
from app.services.model_catalog import (
    InvalidModelParametersError,
    ModelCatalog,
    UnknownModelError,
)
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generations"])


class CreateGenerationRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=8000)
    input_url: str | None = Field(default=None, max_length=4000)
    billing_seconds: int | None = Field(default=None, ge=1, le=600)
    parameters: dict[str, Any] = Field(default_factory=dict)


@router.get("/models")
async def generation_models() -> dict[str, list[dict[str, Any]]]:
    return {"models": ModelCatalog.list()}


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
        "unit_price_rox": str(unit_price),
        "billing_seconds": seconds,
        "cost_rox": str(cost),
    }


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
            billing_seconds=payload.billing_seconds,
            parameters=payload.parameters,
        )
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient ROX") from exc
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": str(generation.id),
        "status": generation.status,
        "model_id": str(generation.parameters.get("_model_id") or ""),
        "cost_rox": str(generation.cost_rox),
        "billing_seconds": (
            str(generation.parameters.get("_billing_seconds"))
            if generation.parameters.get("_billing_seconds") is not None
            else None
        ),
    }
