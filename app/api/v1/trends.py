from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.billing_access import BillingAccessService
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


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


async def _customer_price(
    session: SessionDep,
    *,
    user_id: uuid.UUID,
    item: dict[str, Any],
) -> dict[str, Any]:
    retail = Decimal(str(item.get("cost_credits") or "0"))
    decision = await BillingAccessService.decision(
        session,
        user_id=user_id,
        retail_cost=retail,
    )
    view = dict(item)
    view["retail_cost_credits"] = _amount(decision.retail_cost)
    view["retail_cost_rox"] = _amount(decision.retail_cost)
    view["admin_free"] = decision.admin_free
    view["cost_credits"] = _amount(decision.effective_cost)
    view["cost_rox"] = _amount(decision.effective_cost)
    view["cost_rub"] = _amount(InternalCreditService.rubles_for(decision.effective_cost))
    return view


@router.get("")
async def list_trends(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    media_type: Literal["image", "video"] | None = Query(default=None),
) -> dict[str, object]:
    try:
        payload = await TrendService.list_public(session, limit=limit, media_type=media_type)
        items = [
            await _customer_price(session, user_id=user.id, item=dict(item))
            for item in payload.get("items", [])
        ]
        return {**payload, "items": items}
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.get("/{trend_id}")
async def get_trend(
    trend_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        item = await TrendService.get_public(session, trend_id=trend_id)
        return await _customer_price(session, user_id=user.id, item=item)
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

    params = generation.parameters or {}
    return {
        "id": str(generation.id),
        "task_id": str(generation.id),
        "status": generation.status,
        "cost_credits": format(generation.cost_rox, ".2f"),
        "cost_rox": format(generation.cost_rox, ".2f"),
        "cost_rub": format(InternalCreditService.rubles_for(generation.cost_rox), ".2f"),
        "retail_cost_rox": str(params.get("_retail_cost_rox") or generation.cost_rox),
        "admin_free": bool(params.get("_admin_free", False)),
        "result_url": generation.result_url,
        **trend_meta,
    }
