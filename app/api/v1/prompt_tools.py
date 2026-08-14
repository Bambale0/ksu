from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.abuse_protection import ResourcePolicyError
from app.services.prompt_tools import (
    PromptToolIdempotencyConflict,
    PromptToolPricingService,
    PromptToolService,
    PromptToolUnavailable,
)
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/prompt-tools", tags=["prompt-tools"])


class ImageAnalysisRequest(BaseModel):
    image_url: str = Field(min_length=1, max_length=4000)
    instruction: str = Field(default="", max_length=1000)


class PromptBuilderRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    image_url: str | None = Field(default=None, max_length=4000)
    purpose: Literal["general", "image", "video"] = "general"


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PromptToolUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, PromptToolIdempotencyConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, InsufficientBalanceError):
        return HTTPException(status_code=409, detail="Insufficient credits")
    if isinstance(exc, ResourcePolicyError):
        return HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
async def prompt_tool_catalog(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    _ = user
    return await PromptToolPricingService.catalog(session)


@router.post("/image-analysis", status_code=status.HTTP_202_ACCEPTED)
async def create_image_analysis(
    payload: ImageAnalysisRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    try:
        task, replayed = await PromptToolService.create_task(
            session,
            redis,
            user_id=user.id,
            tool="image_analysis",
            payload=payload.model_dump(),
            idempotency_key=idempotency_key,
        )
        return PromptToolService.public_view(task, replayed=replayed)
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/prompt-builder", status_code=status.HTTP_202_ACCEPTED)
async def create_prompt_builder(
    payload: PromptBuilderRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    try:
        task, replayed = await PromptToolService.create_task(
            session,
            redis,
            user_id=user.id,
            tool="prompt_builder",
            payload=payload.model_dump(),
            idempotency_key=idempotency_key,
        )
        return PromptToolService.public_view(task, replayed=replayed)
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.get("/{task_id}")
async def get_prompt_tool_task(
    task_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        task = await PromptToolService.get_owned(
            session,
            user_id=user.id,
            task_id=task_id,
        )
        return PromptToolService.public_view(task)
    except Exception as exc:
        raise _domain_error(exc) from exc
