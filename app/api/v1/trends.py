from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.credits import InternalCreditService
from app.services.model_catalog import InvalidModelParametersError, UnknownModelError
from app.services.trends import TrendRecipeError, TrendService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/trends", tags=["trends"])


class RunTrendRequest(BaseModel):
    reference_urls: list[str] = Field(default_factory=list, max_length=16)


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, InsufficientBalanceError):
        return HTTPException(status_code=409, detail="Insufficient credits")
    if isinstance(exc, (TrendRecipeError, UnknownModelError, InvalidModelParametersError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Trend operation failed")


@router.get("")
async def list_trends(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    media_type: Literal["image", "video"] | None = Query(default=None),
) -> dict[str, object]:
    _ = user
    try:
        return await TrendService.list_public(session, limit=limit, media_type=media_type)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.get("/{trend_id}")
async def get_trend(
    trend_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    _ = user
    try:
        return await TrendService.get_public(session, trend_id=trend_id)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/{trend_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_trend(
    trend_id: uuid.UUID,
    payload: RunTrendRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    try:
        generation, trend_meta = await TrendService.run(
            session,
            redis,
            user_id=user.id,
            trend_id=trend_id,
            reference_urls=payload.reference_urls,
        )
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc

    return {
        "id": str(generation.id),
        "task_id": str(generation.id),
        "status": generation.status,
        "cost_credits": format(generation.cost_rox, ".2f"),
        "cost_rub": format(InternalCreditService.rubles_for(generation.cost_rox), ".2f"),
        "result_url": generation.result_url,
        **trend_meta,
    }
