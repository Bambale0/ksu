from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, Payment
from app.db.session import get_session
from app.services.admin_cms import AdminCmsService
from app.services.admin_commands import (
    AdminCommandInProgress,
    AdminCommandStoredFailure,
    AdminIdempotencyConflict,
)
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.admin_notifications import AdminNotificationService
from app.services.admin_payments import AdminPaymentService
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.admin_pricing import AdminPricingService
from app.services.admin_reporting import AdminReportingService
from app.services.admin_support import AdminSupportService
from app.services.admin_users import AdminUserConflict, AdminUserNotFound, AdminUserService
from app.services.internal_admin_security import (
    InternalAdminSignature,
    verify_internal_admin_request,
)
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/internal/admin", tags=["internal-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SignatureDep = Annotated[InternalAdminSignature, Depends(verify_internal_admin_request)]


@dataclass(frozen=True, slots=True)
class InternalAdminActor:
    account: AdminAccount
    signature: InternalAdminSignature


@dataclass(frozen=True, slots=True)
class InternalAdminWrite:
    account: AdminAccount
    signature: InternalAdminSignature
    idempotency_key: str
    confirmed: bool
    step_up_valid: bool


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "confirm", "confirmed"}


async def get_internal_admin_actor(
    signature: SignatureDep,
    session: SessionDep,
    x_admin_user_id: Annotated[str | None, Header(alias="X-Admin-User-Id")] = None,
) -> InternalAdminActor:
    if not x_admin_user_id:
        raise HTTPException(status_code=401, detail="Missing X-Admin-User-Id")
    try:
        raw_id = uuid.UUID(x_admin_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid X-Admin-User-Id") from exc
    account = await session.scalar(
        select(AdminAccount).where(
            or_(AdminAccount.id == raw_id, AdminAccount.user_id == raw_id)
        )
    )
    if account is None or not account.is_active:
        raise HTTPException(status_code=403, detail="Admin account is not active")
    return InternalAdminActor(account=account, signature=signature)


ActorDep = Annotated[InternalAdminActor, Depends(get_internal_admin_actor)]


async def get_internal_admin_write(
    actor: ActorDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_admin_confirm: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
    x_admin_step_up: Annotated[str | None, Header(alias="X-Admin-Step-Up")] = None,
) -> InternalAdminWrite:
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 160:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key is required")
    return InternalAdminWrite(
        account=actor.account,
        signature=actor.signature,
        idempotency_key=key,
        confirmed=_truthy(x_admin_confirm),
        step_up_valid=_truthy(x_admin_step_up),
    )


WriteDep = Annotated[InternalAdminWrite, Depends(get_internal_admin_write)]


class UserBlockRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class BalanceAdjustmentRequest(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=5, max_length=500)


class TariffPublishRequest(BaseModel):
    payload: dict[str, Any]


class OperationRefundRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class TicketAssignRequest(BaseModel):
    assigned_admin_id: uuid.UUID | None = None


class TicketUpdateRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None


class TicketReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CmsSaveRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=160)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=500_000)


class CmsPublishRequest(BaseModel):
    version_id: uuid.UUID | None = None


class CampaignPreviewRequest(BaseModel):
    segment: dict[str, Any] = Field(default_factory=dict)
    message: dict[str, Any]


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    segment: dict[str, Any] = Field(default_factory=dict)
    message: dict[str, Any]


class CampaignTestRequest(BaseModel):
    test_user_id: uuid.UUID


def _translate_domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (LookupError, AdminUserNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            AdminPolicyError,
            AdminIdempotencyConflict,
            AdminCommandInProgress,
            AdminCommandStoredFailure,
            AdminUserConflict,
            InsufficientBalanceError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Admin command failed")


async def _commit_or_raise(session: AsyncSession, call):  # type: ignore[no-untyped-def]
    try:
        result = await call
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise _translate_domain_error(exc) from exc


@router.get("/health")
async def internal_admin_health(signature: SignatureDep) -> dict[str, Any]:
    return {
        "ok": True,
        "request_id": signature.request_id,
        "auth": "hmac-sha256",
    }


@router.get("/summary")
async def internal_admin_summary(
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminReportingService.summary(session, admin=actor.account)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/users")
async def internal_admin_users(
    actor: ActorDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=128),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        return await AdminUserService.list_users(
            session,
            admin=actor.account,
            q=q,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/users/{user_id}/block")
async def internal_admin_block_user(
    user_id: uuid.UUID,
    payload: UserBlockRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminUserService.set_blocked(
            session,
            admin=write.account,
            user_id=user_id,
            blocked=True,
            reason=payload.reason,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/users/{user_id}/unblock")
async def internal_admin_unblock_user(
    user_id: uuid.UUID,
    payload: UserBlockRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminUserService.set_blocked(
            session,
            admin=write.account,
            user_id=user_id,
            blocked=False,
            reason=payload.reason,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/users/{user_id}/balance-adjustments")
async def internal_admin_balance_adjustment(
    user_id: uuid.UUID,
    payload: BalanceAdjustmentRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminUserService.adjust_balance(
            session,
            admin=write.account,
            user_id=user_id,
            amount=payload.amount,
            reason=payload.reason,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/generations")
async def internal_admin_generations(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        return await AdminReportingService.generations(
            session,
            admin=actor.account,
            status=status_filter,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/finance")
async def internal_admin_finance(actor: ActorDep, session: SessionDep) -> dict[str, Any]:
    try:
        return await AdminReportingService.finance(session, admin=actor.account)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/payments")
async def internal_admin_payments(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    provider: str | None = Query(default=None, max_length=64),
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        return await AdminReportingService.payments(
            session,
            admin=actor.account,
            status=status_filter,
            provider=provider,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/payments/{payment_id}")
async def internal_admin_payment(
    payment_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        AdminPolicy.require_permission(actor.account, "payments.read")
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise LookupError("Payment not found")
        return AdminReportingService.payment_view(payment)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/payments/{payment_id}/recheck")
async def internal_admin_payment_recheck(
    payment_id: uuid.UUID,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminPaymentService.recheck(
            session,
            admin=write.account,
            payment_id=payment_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/payments/{payment_id}/reprocess")
async def internal_admin_payment_reprocess(
    payment_id: uuid.UUID,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminPaymentService.reprocess(
            session,
            admin=write.account,
            payment_id=payment_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/tariffs")
async def internal_admin_tariffs(actor: ActorDep, session: SessionDep) -> dict[str, Any]:
    try:
        current = await AdminPricingService.current(session, admin=actor.account)
        return {"current": current}
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/tariffs/versions")
async def internal_admin_tariff_versions(
    actor: ActorDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    try:
        return await AdminPricingService.list_versions(session, admin=actor.account, limit=limit)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/tariffs/versions/{version_id}")
async def internal_admin_tariff_version(
    version_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminPricingService.get_version(
            session,
            admin=actor.account,
            version_id=version_id,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/tariffs/publish")
async def internal_admin_publish_tariffs(
    payload: TariffPublishRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminPricingService.publish(
            session,
            admin=write.account,
            payload=payload.payload,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/operations")
async def internal_admin_operations(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        return await AdminGenerationOperationService.list_operations(
            session,
            admin=actor.account,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/operations/{operation_id}")
async def internal_admin_operation(
    operation_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminGenerationOperationService.get_operation(
            session,
            admin=actor.account,
            operation_id=operation_id,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/operations/{operation_id}/timeline")
async def internal_admin_operation_timeline(
    operation_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        items = await AdminGenerationOperationService.timeline(
            session,
            admin=actor.account,
            operation_id=operation_id,
        )
        return {"items": items}
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/operations/{operation_id}/replay")
async def internal_admin_operation_replay(
    operation_id: uuid.UUID,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminGenerationOperationService.replay_operation(
            session,
            admin=write.account,
            operation_id=operation_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/operations/{operation_id}/refund")
async def internal_admin_operation_refund(
    operation_id: uuid.UUID,
    payload: OperationRefundRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminGenerationOperationService.refund_operation(
            session,
            admin=write.account,
            operation_id=operation_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
            reason=payload.reason,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/tickets")
async def internal_admin_tickets(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    try:
        return await AdminSupportService.list_tickets(
            session,
            admin=actor.account,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/tickets/{ticket_id}")
async def internal_admin_ticket(
    ticket_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminSupportService.get_ticket(
            session,
            admin=actor.account,
            ticket_id=ticket_id,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/tickets/{ticket_id}/assign")
async def internal_admin_ticket_assign(
    ticket_id: uuid.UUID,
    payload: TicketAssignRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminSupportService.assign_ticket(
            session,
            admin=write.account,
            ticket_id=ticket_id,
            assigned_admin_id=payload.assigned_admin_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=True,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/tickets/{ticket_id}/update")
async def internal_admin_ticket_update(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    if payload.status is None and payload.priority is None:
        raise HTTPException(status_code=422, detail="No ticket changes supplied")
    result, replayed = await _commit_or_raise(
        session,
        AdminSupportService.update_ticket(
            session,
            admin=write.account,
            ticket_id=ticket_id,
            status=payload.status,
            priority=payload.priority,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/tickets/{ticket_id}/reply")
async def internal_admin_ticket_reply(
    ticket_id: uuid.UUID,
    payload: TicketReplyRequest,
    request: Request,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminSupportService.reply_ticket(
            session,
            admin=write.account,
            ticket_id=ticket_id,
            body=payload.body,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            request=request,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/cms/documents")
async def internal_admin_cms_documents(
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminCmsService.list_documents(session, admin=actor.account)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/cms/documents/{document_id}")
async def internal_admin_cms_document(
    document_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminCmsService.get_document(
            session,
            admin=actor.account,
            document_id=document_id,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/cms/documents", status_code=status.HTTP_201_CREATED)
async def internal_admin_cms_save(
    payload: CmsSaveRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminCmsService.save_document(
            session,
            admin=write.account,
            slug=payload.slug,
            title=payload.title,
            body=payload.body,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/cms/documents/{document_id}/publish")
async def internal_admin_cms_publish(
    document_id: uuid.UUID,
    payload: CmsPublishRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminCmsService.publish_document(
            session,
            admin=write.account,
            document_id=document_id,
            version_id=payload.version_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/preview")
async def internal_admin_notification_preview(
    payload: CampaignPreviewRequest,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminNotificationService.preview_campaign(
            session,
            admin=actor.account,
            segment=payload.segment,
            message=payload.message,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.get("/notifications/campaigns")
async def internal_admin_campaigns(
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminNotificationService.list_campaigns(session, admin=actor.account)
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/notifications/campaigns", status_code=status.HTTP_201_CREATED)
async def internal_admin_campaign_create(
    payload: CampaignCreateRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminNotificationService.create_campaign(
            session,
            admin=write.account,
            name=payload.name,
            segment=payload.segment,
            message=payload.message,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/notifications/campaigns/{campaign_id}")
async def internal_admin_campaign(
    campaign_id: uuid.UUID,
    actor: ActorDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminNotificationService.get_campaign(
            session,
            admin=actor.account,
            campaign_id=campaign_id,
        )
    except Exception as exc:
        raise _translate_domain_error(exc) from exc


@router.post("/notifications/campaigns/{campaign_id}/test")
async def internal_admin_campaign_test(
    campaign_id: uuid.UUID,
    payload: CampaignTestRequest,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminNotificationService.test_campaign(
            session,
            admin=write.account,
            campaign_id=campaign_id,
            test_user_id=payload.test_user_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/campaigns/{campaign_id}/start")
async def internal_admin_campaign_start(
    campaign_id: uuid.UUID,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminNotificationService.start_campaign(
            session,
            admin=write.account,
            campaign_id=campaign_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
            step_up_valid=write.step_up_valid,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/campaigns/{campaign_id}/cancel")
async def internal_admin_campaign_cancel(
    campaign_id: uuid.UUID,
    write: WriteDep,
    session: SessionDep,
) -> dict[str, Any]:
    result, replayed = await _commit_or_raise(
        session,
        AdminNotificationService.cancel_campaign(
            session,
            admin=write.account,
            campaign_id=campaign_id,
            idempotency_key=write.idempotency_key,
            request_id=write.signature.request_id,
            confirmed=write.confirmed,
        ),
    )
    return {**result, "idempotency_replayed": replayed}
