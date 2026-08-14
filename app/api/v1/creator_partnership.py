from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from app.api.deps import CurrentUserDep, SessionDep
from app.services.creator_partnership import (
    CreatorPartnershipConflict,
    CreatorPartnershipService,
)

router = APIRouter(prefix="/creator-partnership", tags=["creator-partnership"])


class CreatorApplicationRequest(BaseModel):
    channel_name: str = Field(min_length=2, max_length=160)
    channel_url: HttpUrl
    audience_size: int = Field(ge=1, le=100_000_000)
    average_views: int | None = Field(default=None, ge=0, le=100_000_000)
    cooperation_format: str = Field(min_length=2, max_length=160)
    message: str = Field(default="", max_length=4000)


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CreatorPartnershipConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
async def creator_partnership_status(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    return await CreatorPartnershipService.status(session, user_id=user.id)


@router.post("/applications", status_code=status.HTTP_201_CREATED)
async def submit_creator_application(
    payload: CreatorApplicationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
) -> dict[str, object]:
    try:
        item, replayed = await CreatorPartnershipService.submit_application(
            session,
            user_id=user.id,
            channel_name=payload.channel_name,
            channel_url=str(payload.channel_url),
            audience_size=payload.audience_size,
            average_views=payload.average_views,
            cooperation_format=payload.cooperation_format,
            message=payload.message,
            idempotency_key=idempotency_key,
        )
        await session.commit()
        return {
            "application": CreatorPartnershipService._application_view(item),
            "idempotency_replayed": replayed,
        }
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc
