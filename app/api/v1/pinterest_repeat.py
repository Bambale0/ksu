from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session, redis_client
from app.models.user import User
from app.services.billing_access import BillingAccessService
from app.services.generation import GenerationService, InsufficientBalanceError
from app.services.pinterest_repeat import PinterestRepeatError, PinterestRepeatService

router = APIRouter(prefix="/pinterest-repeat", tags=["pinterest-repeat"])


class PinterestResolveRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class PinterestRepeatRequest(BaseModel):
    scene_reference_url: str = Field(min_length=8, max_length=4096)
    identity_reference_urls: list[str] = Field(min_length=1, max_length=5)
    height_cm: int = Field(ge=120, le=230)
    weight_kg: int = Field(ge=30, le=250)
    expression: str | None = Field(default=None, max_length=240)


def _build(payload: PinterestRepeatRequest):
    try:
        return PinterestRepeatService.build_request(
            scene_reference_url=payload.scene_reference_url,
            identity_reference_urls=payload.identity_reference_urls,
            height_cm=payload.height_cm,
            weight_kg=payload.weight_kg,
            expression=payload.expression,
        )
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/resolve")
async def resolve_pinterest_reference(payload: PinterestResolveRequest) -> dict[str, str]:
    try:
        resolved = await PinterestRepeatService.resolve_reference(payload.url)
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "source_url": resolved.source_url,
        "reference_url": resolved.reference_url,
    }


@router.post("/quote")
async def quote_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> dict[str, object]:
    recipe = _build(payload)
    spec, _clean, retail_cost, seconds, retail_unit_price = await GenerationService.prepare_request(
        session=session,
        model_id=recipe.model_id,
        prompt=recipe.prompt,
        parameters=recipe.parameters,
    )
    billing = await BillingAccessService.decision(
        session,
        user=user,
        requested_cost=retail_cost,
    )
    return {
        "mode": "pinterest_repeat",
        "model_id": recipe.model_id,
        "unit_price_rox": str(retail_unit_price),
        "cost_rox": str(retail_cost),
        "effective_cost_rox": str(billing.effective_cost),
        "cost_rub": str(spec.price_rub),
        "retail_cost_rox": str(retail_cost),
        "billing_seconds": seconds,
        "admin_free": billing.admin_free,
    }


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(redis_client)],
) -> dict[str, object]:
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
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Недостаточно ROX") from exc

    return {
        "id": str(generation.id),
        "status": generation.status,
        "mode": "pinterest_repeat",
        "cost_rox": str(generation.cost_credits),
        "admin_free": generation.cost_credits == 0,
    }
