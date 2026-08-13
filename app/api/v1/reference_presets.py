from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUserDep, SessionDep
from app.services.references import ReferenceError, ReferenceService
from app.services.user_presets import PresetError, UserPresetService

router = APIRouter(tags=["references", "presets"])


class ReferenceCreate(BaseModel):
    source_url: str = Field(min_length=1, max_length=4000)
    kind: str
    label: str = Field(default="", max_length=120)
    original_filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)


class PresetWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(default="", max_length=8000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reference_ids: list[uuid.UUID] = Field(default_factory=list, max_length=16)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ReferenceError, PresetError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, IntegrityError):
        return HTTPException(status_code=409, detail="A preset with this name already exists")
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/references")
async def list_references(
    user: CurrentUserDep,
    session: SessionDep,
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    try:
        rows = await ReferenceService.list_owned(session, user_id=user.id, kind=kind, limit=limit)
        return {"items": [ReferenceService.public_view(row) for row in rows]}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/references", status_code=status.HTTP_201_CREATED)
async def register_reference(
    payload: ReferenceCreate,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        row, replayed = await ReferenceService.register(
            session,
            user_id=user.id,
            source_url=payload.source_url,
            kind=payload.kind,
            label=payload.label,
            original_filename=payload.original_filename,
            content_type=payload.content_type,
        )
        return {**ReferenceService.public_view(row), "replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference(
    reference_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> None:
    try:
        await ReferenceService.remove(session, user_id=user.id, reference_id=reference_id)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.get("/presets")
async def list_presets(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    rows = await UserPresetService.list_owned(session, user_id=user.id)
    return {"items": [UserPresetService.public_view(row) for row in rows]}


@router.post("/presets", status_code=status.HTTP_201_CREATED)
async def create_preset(
    payload: PresetWrite,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        row = await UserPresetService.create(
            session, user_id=user.id, **payload.model_dump()
        )
        return UserPresetService.public_view(row)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.put("/presets/{preset_id}")
async def update_preset(
    preset_id: uuid.UUID,
    payload: PresetWrite,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        row = await UserPresetService.update(
            session, user_id=user.id, preset_id=preset_id, **payload.model_dump()
        )
        return UserPresetService.public_view(row)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> None:
    try:
        await UserPresetService.remove(session, user_id=user.id, preset_id=preset_id)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc
