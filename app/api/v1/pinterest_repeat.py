from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, UnknownModelError
from app.services.pinterest_repeat import (
    PinterestRepeatError,
    PinterestRepeatGenerationRequest,
    PinterestRepeatService,
)
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/pinterest-repeat", tags=["pinterest-repeat"])


class PinterestResolveRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class PinterestRepeatRequest(BaseModel):
    scene_reference_url: str = Field(min_length=8, max_length=4096)
    identity_reference_urls: list[str] = Field(min_length=1, max_length=5)
    height_cm: int = Field(ge=120, le=230)
    weight_kg: int = Field(ge=30, le=250)
    expression: str | None = Field(default=None, max_length=240)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _build(payload: PinterestRepeatRequest) -> PinterestRepeatGenerationRequest:
    try:
        return PinterestRepeatService.build_request(
            scene_reference_url=payload.scene_reference_url,
            identity_reference_urls=payload.identity_reference_urls,
            height_cm=payload.height_cm,
            weight_kg=payload.weight_kg,
            expression=payload.expression,
        )
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/resolve")
async def resolve_pinterest_reference(payload: PinterestResolveRequest) -> dict[str, str]:
    try:
        resolved = await PinterestRepeatService.resolve_reference(payload.url)
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "source_url": resolved.source_url,
        "reference_url": resolved.reference_url,
    }


@router.post("/quote")
async def quote_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    recipe = _build(payload)
    try:
        spec, _clean, retail_cost, seconds, retail_unit_price = await GenerationService.prepare_request(
            session,
            model_id=recipe.model_id,
            prompt=recipe.prompt,
            parameters=recipe.parameters,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    billing = await BillingAccessService.decision(
        session,
        user_id=user.id,
        retail_cost=retail_cost,
    )
    effective = billing.effective_cost
    return {
        "mode": "pinterest_repeat",
        "model_id": spec.id,
        "unit_price_rox": _amount(retail_unit_price),
        "cost_rox": _amount(retail_cost),
        "effective_cost_rox": _amount(effective),
        "cost_rub": _amount(InternalCreditService.rubles_for(effective)),
        "retail_cost_rox": _amount(retail_cost),
        "billing_seconds": seconds,
        "admin_free": billing.admin_free,
    }


@router.post("/run", status_code=202)
async def run_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, Any]:
    recipe = _build(payload)
    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            model_id=recipe.model_id,
            prompt=recipe.prompt,
            parameters=recipe.parameters,
            action_type="pinterest_repeat",
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Недостаточно ROX") from exc

    return {
        "id": str(generation.id),
        "status": generation.status,
        "mode": "pinterest_repeat",
        "cost_rox": _amount(generation.cost_rox),
        "admin_free": bool((generation.parameters or {}).get("_admin_free")),
    }
