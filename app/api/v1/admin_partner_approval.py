from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.services.admin_partners import AdminPartnerService
from app.services.admin_security import AdminAuthService

router = APIRouter(prefix="/admin/partner-applications", tags=["admin-partner-applications"])

PartnerReadDep = Annotated[
    AdminContext,
    Depends(require_permission("partners.read")),
]
PartnerWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("partners.manage", step_up=True)),
]


class PartnerApplicationStateRequest(BaseModel):
    status: Literal["approved", "rejected", "suspended"]
    reason: str = Field(min_length=3, max_length=1000)


def _request_id(request: Request) -> str:
    return str(
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or ""
    )


@router.get("")
async def list_partner_applications(
    context: PartnerReadDep,
    session: SessionDep,
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    return await AdminPartnerService.list_applications(
        session,
        admin=context.account,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/{user_id}/state")
async def update_partner_application(
    user_id: uuid.UUID,
    payload: PartnerApplicationStateRequest,
    request: Request,
    context: PartnerWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, object]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    try:
        result, replayed = await AdminPartnerService.update_application(
            session,
            admin=context.account,
            user_id=user_id,
            status=payload.status,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            request_id=_request_id(request),
            confirmed=(confirmation or "").strip().upper() == "CONFIRM",
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Partner application not found") from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
