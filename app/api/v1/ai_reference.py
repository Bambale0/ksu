from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.ai_reference import (
    AiReferenceError,
    AiReferenceGenerationRequest,
    AiReferenceScenario,
    AiReferenceService,
    AiReferenceSubject,
)
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, UnknownModelError
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/ai-reference", tags=["ai-reference"])


class AiReferenceRequest(BaseModel):
    scenario: AiReferenceScenario
    subject: AiReferenceSubject | None = None
    reference_urls: list[str] = Field(min_length=1, max_length=4)
    instruction: str | None = Field(default=None, max_length=1200)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _build(payload: AiReferenceRequest) -> AiReferenceGenerationRequest:
    try:
        return AiReferenceService.build_request(
            scenario=payload.scenario,
            subject=payload.subject,
            reference_urls=payload.reference_urls,
            instruction=payload.instruction,
        )
    except AiReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/quote")
async def quote_ai_reference(
    payload: AiReferenceRequest,
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
        "scenario": payload.scenario,
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
async def run_ai_reference(
    payload: AiReferenceRequest,
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
            action_type="ai_reference",
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Недостаточно ROX") from exc

    return {
        "id": str(generation.id),
        "status": generation.status,
        "scenario": payload.scenario,
        "cost_rox": _amount(generation.cost_rox),
        "admin_free": bool((generation.parameters or {}).get("_admin_free")),
    }
