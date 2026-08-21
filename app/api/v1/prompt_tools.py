from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

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

_ALLOWED_SEEDANCE_DURATIONS = {5, 10, 15}


class ImageAnalysisRequest(BaseModel):
    image_url: str = Field(min_length=1, max_length=4000)
    instruction: str = Field(default="", max_length=1000)


class PromptBuilderRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    image_url: str | None = Field(default=None, max_length=4000)
    purpose: Literal["general", "image", "video", "seedance"] = "general"
    duration_seconds: int | None = Field(default=None)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in _ALLOWED_SEEDANCE_DURATIONS:
            raise ValueError("duration_seconds must be 5, 10 or 15")
        return value


class VideoPromptRequest(BaseModel):
    video_url: str = Field(min_length=1, max_length=4000)
    instruction: str = Field(default="", max_length=1000)
    duration_seconds: int | None = Field(default=None)

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in _ALLOWED_SEEDANCE_DURATIONS:
            raise ValueError("duration_seconds must be 5, 10 or 15")
        return value


_PURPOSE_CONTEXT = {
    "image": (
        "Сформируй production-ready prompt именно для генерации статичного изображения. "
        "Сделай явными композицию, оптику/ракурс, свет, материалы, палитру и визуальный стиль."
    ),
    "video": (
        "Сформируй production-ready prompt именно для генерации видео. "
        "Опиши действие по времени, движение камеры и объектов, динамику сцены, свет, "
        "непрерывность кадров и финальное состояние."
    ),
    "seedance": (
        "Сформируй production-ready prompt для Seedance/video-моделей: короткая сцена, "
        "понятная режиссура, камера, движение объектов, свет, финальное состояние и negative prompt."
    ),
}


def _prompt_builder_payload(payload: PromptBuilderRequest) -> dict[str, str | int | None]:
    text = payload.text.strip()
    context = _PURPOSE_CONTEXT.get(payload.purpose)
    if payload.duration_seconds:
        duration = f"Целевая длительность ролика: {payload.duration_seconds} секунд."
        context = f"{context} {duration}" if context else duration
    if context:
        text = f"{context}\n\nИдея пользователя: {text}" if text else context
    return {
        "text": text,
        "image_url": payload.image_url,
        "duration_seconds": payload.duration_seconds,
    }


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
    return await PromptToolPricingService.catalog(session, user_id=user.id)


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
            payload=_prompt_builder_payload(payload),
            idempotency_key=idempotency_key,
        )
        return PromptToolService.public_view(task, replayed=replayed)
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/video-prompt", status_code=status.HTTP_202_ACCEPTED)
async def create_video_prompt(
    payload: VideoPromptRequest,
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
            tool="video_prompt",
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
