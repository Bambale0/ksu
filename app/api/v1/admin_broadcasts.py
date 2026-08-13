from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.broadcast_models import BroadcastCampaign
from app.services.admin_security import AdminAuditService
from app.services.broadcasts import BroadcastCampaignError, BroadcastService

router = APIRouter(prefix="/admin/broadcasts", tags=["admin-broadcasts"])

BroadcastReadDep = Annotated[
    AdminContext,
    Depends(require_permission("broadcasts.read")),
]
BroadcastManageDep = Annotated[
    AdminContext,
    Depends(require_permission("broadcasts.manage")),
]
BroadcastStepUpDep = Annotated[
    AdminContext,
    Depends(require_permission("broadcasts.manage", step_up=True)),
]


class CreateBroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)


@router.get("/preview")
async def preview_audience(
    _context: BroadcastManageDep,
    session: SessionDep,
) -> dict[str, object]:
    count = await BroadcastService.eligible_count(session)
    return {
        "eligible_count": count,
        "audience": {
            "active_only": True,
            "notifications_enabled": True,
            "marketing_notifications": True,
        },
    }


@router.get("")
async def list_campaigns(
    _context: BroadcastReadDep,
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    limit = max(1, min(limit, 100))
    offset = max(0, min(offset, 100_000))
    total = int((await session.scalar(select(func.count()).select_from(BroadcastCampaign))) or 0)
    rows = list(
        (
            await session.scalars(
                select(BroadcastCampaign)
                .order_by(BroadcastCampaign.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return {
        "items": [await BroadcastService.view(session, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    _context: BroadcastReadDep,
    session: SessionDep,
) -> dict[str, object]:
    campaign = await session.get(BroadcastCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return await BroadcastService.view(session, campaign)


@router.post("", status_code=201)
async def create_campaign(
    payload: CreateBroadcastRequest,
    request: Request,
    context: BroadcastManageDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        campaign = await BroadcastService.create_draft(
            session,
            admin_id=context.account.id,
            title=payload.title,
            body=payload.body,
        )
    except BroadcastCampaignError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await AdminAuditService.record(
        session,
        action="admin.broadcast.created",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="broadcast_campaign",
        resource_id=str(campaign.id),
        metadata={"title": campaign.title},
    )
    await session.commit()
    return await BroadcastService.view(session, campaign)


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    context: BroadcastStepUpDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        campaign = await BroadcastService.launch(session, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BroadcastCampaignError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await AdminAuditService.record(
        session,
        action="admin.broadcast.launched",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="broadcast_campaign",
        resource_id=str(campaign.id),
        metadata={"eligible_count": campaign.eligible_count},
    )
    await session.commit()
    return await BroadcastService.view(session, campaign)


@router.post("/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    context: BroadcastStepUpDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        campaign = await BroadcastService.cancel(session, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BroadcastCampaignError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await AdminAuditService.record(
        session,
        action="admin.broadcast.canceled",
        outcome="success",
        admin=context.account,
        admin_session=context.session,
        request=request,
        resource_type="broadcast_campaign",
        resource_id=str(campaign.id),
    )
    await session.commit()
    return await BroadcastService.view(session, campaign)
