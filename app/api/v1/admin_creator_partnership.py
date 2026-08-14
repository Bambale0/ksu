from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.creator_partner_models import (
    CreatorPartnershipAgreement,
    CreatorPartnershipGrant,
)
from app.db.models import User
from app.services.admin_commands import (
    AdminCommandInProgress,
    AdminCommandStoredFailure,
    AdminIdempotencyConflict,
)
from app.services.admin_policy import AdminPolicyError
from app.services.admin_security import AdminAuthService
from app.services.creator_partnership import (
    CreatorPartnershipConflict,
    CreatorPartnershipService,
)

router = APIRouter(prefix="/admin/creator-partnership", tags=["admin-creator-partnership"])

CreatorReadDep = Annotated[AdminContext, Depends(require_permission("partners.read"))]
CreatorManageDep = Annotated[AdminContext, Depends(require_permission("partners.manage"))]


class CreatorDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    decision_note: str = Field(default="", max_length=4000)
    terms_summary: str | None = Field(default=None, max_length=4000)
    monthly_rox: Decimal | None = Field(default=None, gt=0, le=1_000_000)
    terms: dict[str, Any] = Field(default_factory=dict)
    starts_on: date | None = None
    ends_on: date | None = None


class CreatorAgreementUpdateRequest(BaseModel):
    status: Literal["active", "paused", "ended"]
    terms_summary: str = Field(min_length=2, max_length=4000)
    monthly_rox: Decimal = Field(gt=0, le=1_000_000)
    terms: dict[str, Any] = Field(default_factory=dict)
    ends_on: date | None = None
    reason: str = Field(min_length=3, max_length=1000)


class CreatorGrantRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    note: str = Field(default="", max_length=1000)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4())


def _confirmed(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "confirm", "confirmed"}


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (CreatorPartnershipConflict, AdminIdempotencyConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AdminCommandInProgress):
        return HTTPException(status_code=409, detail=str(exc), headers={"Retry-After": "2"})
    if isinstance(exc, AdminCommandStoredFailure):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AdminPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/applications")
async def list_creator_applications(
    context: CreatorReadDep,
    session: SessionDep,
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    _ = context
    return await CreatorPartnershipService.list_applications(
        session,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/agreements")
async def list_creator_agreements(
    context: CreatorReadDep,
    session: SessionDep,
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    _ = context
    stmt = select(CreatorPartnershipAgreement, User).join(
        User, User.id == CreatorPartnershipAgreement.user_id
    )
    count_stmt = select(func.count()).select_from(CreatorPartnershipAgreement)
    if status:
        stmt = stmt.where(CreatorPartnershipAgreement.status == status)
        count_stmt = count_stmt.where(CreatorPartnershipAgreement.status == status)
    rows = (
        await session.execute(
            stmt.order_by(CreatorPartnershipAgreement.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items: list[dict[str, object]] = []
    for agreement, user in rows:
        grants = list(
            (
                await session.scalars(
                    select(CreatorPartnershipGrant)
                    .where(CreatorPartnershipGrant.agreement_id == agreement.id)
                    .order_by(CreatorPartnershipGrant.period.desc())
                    .limit(12)
                )
            ).all()
        )
        items.append(
            {
                **CreatorPartnershipService._agreement_view(agreement),
                "user": {
                    "id": str(user.id),
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                },
                "grants": [CreatorPartnershipService._grant_view(item) for item in grants],
            }
        )
    return {
        "items": items,
        "total": int((await session.scalar(count_stmt)) or 0),
        "limit": limit,
        "offset": offset,
    }


@router.post("/applications/{application_id}/decision")
async def decide_creator_application(
    application_id: uuid.UUID,
    payload: CreatorDecisionRequest,
    request: Request,
    context: CreatorManageDep,
    session: SessionDep,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    x_confirm_action: str | None = Header(default=None, alias="X-Confirm-Action"),
) -> dict[str, object]:
    try:
        result, replayed = await CreatorPartnershipService.decide_application(
            session,
            admin=context.account,
            application_id=application_id,
            decision=payload.decision,
            decision_note=payload.decision_note,
            terms_summary=payload.terms_summary,
            monthly_rox=payload.monthly_rox,
            terms=payload.terms,
            starts_on=payload.starts_on,
            ends_on=payload.ends_on,
            idempotency_key=idempotency_key,
            request_id=_request_id(request),
            confirmed=_confirmed(x_confirm_action),
            request=request,
            admin_session=context.session,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.patch("/agreements/{agreement_id}")
async def update_creator_agreement(
    agreement_id: uuid.UUID,
    payload: CreatorAgreementUpdateRequest,
    request: Request,
    context: CreatorManageDep,
    session: SessionDep,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    x_confirm_action: str | None = Header(default=None, alias="X-Confirm-Action"),
) -> dict[str, object]:
    try:
        result, replayed = await CreatorPartnershipService.update_agreement(
            session,
            admin=context.account,
            agreement_id=agreement_id,
            status=payload.status,
            terms_summary=payload.terms_summary,
            monthly_rox=payload.monthly_rox,
            terms=payload.terms,
            ends_on=payload.ends_on,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            request_id=_request_id(request),
            confirmed=_confirmed(x_confirm_action),
            request=request,
            admin_session=context.session,
        )
        await session.commit()
        return {"agreement": result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/agreements/{agreement_id}/grants")
async def grant_creator_period(
    agreement_id: uuid.UUID,
    payload: CreatorGrantRequest,
    request: Request,
    context: CreatorManageDep,
    session: SessionDep,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    x_confirm_action: str | None = Header(default=None, alias="X-Confirm-Action"),
) -> dict[str, object]:
    try:
        result, replayed = await CreatorPartnershipService.admin_grant(
            session,
            admin=context.account,
            agreement_id=agreement_id,
            period=payload.period,
            note=payload.note,
            idempotency_key=idempotency_key,
            request_id=_request_id(request),
            confirmed=_confirmed(x_confirm_action),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
            request=request,
            admin_session=context.session,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc
