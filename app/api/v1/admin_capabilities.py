from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.services.admin_cms import AdminCmsService
from app.services.admin_content import AdminContentService
from app.services.admin_notifications import AdminNotificationService
from app.services.admin_partners import AdminPartnerService
from app.services.admin_policy import AdminPolicyError
from app.services.admin_pricing import AdminPricingService
from app.services.admin_promos import AdminPromoService
from app.services.admin_runtime import AdminRuntimeService
from app.services.admin_security import AdminAuthService
from app.services.admin_support import AdminSupportService

router = APIRouter(prefix="/admin", tags=["admin-capabilities"])

AdminDashboardDep = Annotated[
    AdminContext,
    Depends(require_permission("dashboard.read")),
]
AdminPricingReadDep = Annotated[
    AdminContext,
    Depends(require_permission("pricing.read")),
]
AdminPricingWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("pricing.manage", step_up=True)),
]
AdminSupportReadDep = Annotated[
    AdminContext,
    Depends(require_permission("support.read")),
]
AdminSupportWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("support.manage")),
]
AdminNotificationsReadDep = Annotated[
    AdminContext,
    Depends(require_permission("notifications.read")),
]
AdminNotificationsWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("notifications.manage")),
]
AdminNotificationsSensitiveDep = Annotated[
    AdminContext,
    Depends(require_permission("notifications.manage", step_up=True)),
]
AdminCmsReadDep = Annotated[
    AdminContext,
    Depends(require_permission("cms.read")),
]
AdminCmsWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("cms.manage")),
]
AdminPromptReadDep = Annotated[
    AdminContext,
    Depends(require_permission("prompts.read")),
]
AdminPromptWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("prompts.manage")),
]
AdminSocialDep = Annotated[
    AdminContext,
    Depends(require_permission("social.moderate")),
]
AdminRuntimeDep = Annotated[
    AdminContext,
    Depends(require_permission("runtime.manage")),
]
AdminPartnerReadDep = Annotated[
    AdminContext,
    Depends(require_permission("partners.read")),
]
AdminPartnerWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("partners.manage", step_up=True)),
]
AdminPromoReadDep = Annotated[
    AdminContext,
    Depends(require_permission("promocodes.read")),
]
AdminPromoWriteDep = Annotated[
    AdminContext,
    Depends(require_permission("promocodes.manage")),
]


class TariffPublishRequest(BaseModel):
    payload: dict[str, Any]


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


class SupportAssignRequest(BaseModel):
    assigned_admin_id: uuid.UUID | None = None


class SupportUpdateRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None


class SupportReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    reward_credits: Decimal = Field(gt=0)
    max_uses: int | None = Field(default=None, ge=1, le=10_000_000)
    expires_at: datetime | None = None


class PromoStateRequest(BaseModel):
    is_active: bool


class PromptModerationRequest(BaseModel):
    action: Literal["approve", "reject", "deactivate"]
    reason: str = Field(min_length=3, max_length=1000)


class TrendCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


class FeedModerationRequest(BaseModel):
    state: Literal["visible", "blurred", "removed"]
    reason: str = Field(min_length=3, max_length=1000)


class RuntimeSubscriptionRequest(BaseModel):
    enabled: bool


class WithdrawalStateRequest(BaseModel):
    status: Literal["processing", "paid", "rejected", "canceled"]
    reason: str = Field(min_length=3, max_length=500)


def _confirmed(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "confirm", "confirmed"}


def _require_idempotency(value: str | None) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 160:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key is required")
    return key


def _request_id(request: Request) -> str:
    value = str(request.headers.get("X-Request-Id") or "").strip()
    return value[:96] if value else f"web:{uuid.uuid4()}"


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AdminPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


async def _commit(session: SessionDep, awaitable):  # type: ignore[no-untyped-def]
    try:
        result = await awaitable
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.get("/tariffs")
async def web_admin_tariffs(context: AdminPricingReadDep, session: SessionDep) -> dict[str, Any]:
    return {
        "current": await AdminPricingService.current(session, admin=context.account),
        "versions": (
            await AdminPricingService.list_versions(session, admin=context.account, limit=100)
        )["items"],
    }


@router.post("/tariffs/publish")
async def web_admin_tariffs_publish(
    payload: TariffPublishRequest,
    request: Request,
    context: AdminPricingWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPricingService.publish(
            session,
            admin=context.account,
            payload=payload.payload,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/support/tickets")
async def web_admin_support_tickets(
    context: AdminSupportReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    return await AdminSupportService.list_tickets(
        session,
        admin=context.account,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/support/tickets/{ticket_id}")
async def web_admin_support_ticket(
    ticket_id: uuid.UUID,
    context: AdminSupportReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminSupportService.get_ticket(
            session,
            admin=context.account,
            ticket_id=ticket_id,
        )
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/support/tickets/{ticket_id}/assign")
async def web_admin_support_assign(
    ticket_id: uuid.UUID,
    payload: SupportAssignRequest,
    request: Request,
    context: AdminSupportWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminSupportService.assign_ticket(
            session,
            admin=context.account,
            ticket_id=ticket_id,
            assigned_admin_id=payload.assigned_admin_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/support/tickets/{ticket_id}/update")
async def web_admin_support_update(
    ticket_id: uuid.UUID,
    payload: SupportUpdateRequest,
    request: Request,
    context: AdminSupportWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if payload.status is None and payload.priority is None:
        raise HTTPException(status_code=422, detail="No ticket changes supplied")
    result, replayed = await _commit(
        session,
        AdminSupportService.update_ticket(
            session,
            admin=context.account,
            ticket_id=ticket_id,
            status=payload.status,
            priority=payload.priority,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/support/tickets/{ticket_id}/reply")
async def web_admin_support_reply(
    ticket_id: uuid.UUID,
    payload: SupportReplyRequest,
    request: Request,
    context: AdminSupportWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminSupportService.reply_ticket(
            session,
            admin=context.account,
            ticket_id=ticket_id,
            body=payload.body,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/cms/documents")
async def web_admin_cms_documents(context: AdminCmsReadDep, session: SessionDep) -> dict[str, Any]:
    return await AdminCmsService.list_documents(session, admin=context.account)


@router.get("/cms/documents/{document_id}")
async def web_admin_cms_document(
    document_id: uuid.UUID,
    context: AdminCmsReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminCmsService.get_document(
            session,
            admin=context.account,
            document_id=document_id,
        )
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/cms/documents", status_code=status.HTTP_201_CREATED)
async def web_admin_cms_save(
    payload: CmsSaveRequest,
    request: Request,
    context: AdminCmsWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminCmsService.save_document(
            session,
            admin=context.account,
            slug=payload.slug,
            title=payload.title,
            body=payload.body,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/cms/documents/{document_id}/publish")
async def web_admin_cms_publish(
    document_id: uuid.UUID,
    payload: CmsPublishRequest,
    request: Request,
    context: AdminCmsWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminCmsService.publish_document(
            session,
            admin=context.account,
            document_id=document_id,
            version_id=payload.version_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/preview")
async def web_admin_notification_preview(
    payload: CampaignPreviewRequest,
    context: AdminNotificationsReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminNotificationService.preview_campaign(
            session,
            admin=context.account,
            segment=payload.segment,
            message=payload.message,
        )
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.get("/notifications/campaigns")
async def web_admin_campaigns(
    context: AdminNotificationsReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    return await AdminNotificationService.list_campaigns(session, admin=context.account)


@router.get("/notifications/campaigns/{campaign_id}")
async def web_admin_campaign(
    campaign_id: uuid.UUID,
    context: AdminNotificationsReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminNotificationService.get_campaign(
            session,
            admin=context.account,
            campaign_id=campaign_id,
        )
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/notifications/campaigns", status_code=status.HTTP_201_CREATED)
async def web_admin_campaign_create(
    payload: CampaignCreateRequest,
    request: Request,
    context: AdminNotificationsWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminNotificationService.create_campaign(
            session,
            admin=context.account,
            name=payload.name,
            segment=payload.segment,
            message=payload.message,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/campaigns/{campaign_id}/test")
async def web_admin_campaign_test(
    campaign_id: uuid.UUID,
    payload: CampaignTestRequest,
    request: Request,
    context: AdminNotificationsWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminNotificationService.test_campaign(
            session,
            admin=context.account,
            campaign_id=campaign_id,
            test_user_id=payload.test_user_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/campaigns/{campaign_id}/start")
async def web_admin_campaign_start(
    campaign_id: uuid.UUID,
    request: Request,
    context: AdminNotificationsSensitiveDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminNotificationService.start_campaign(
            session,
            admin=context.account,
            campaign_id=campaign_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/notifications/campaigns/{campaign_id}/cancel")
async def web_admin_campaign_cancel(
    campaign_id: uuid.UUID,
    request: Request,
    context: AdminNotificationsWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminNotificationService.cancel_campaign(
            session,
            admin=context.account,
            campaign_id=campaign_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/promocodes")
async def web_admin_promos(
    context: AdminPromoReadDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    if q:
        try:
            return {"item": await AdminPromoService.lookup(session, admin=context.account, query=q)}
        except Exception as exc:
            raise _domain_error(exc) from exc
    return await AdminPromoService.list_promos(session, admin=context.account)


@router.post("/promocodes", status_code=status.HTTP_201_CREATED)
async def web_admin_promo_create(
    payload: PromoCreateRequest,
    request: Request,
    context: AdminPromoWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPromoService.create(
            session,
            admin=context.account,
            code=payload.code,
            reward_credits=payload.reward_credits,
            max_uses=payload.max_uses,
            expires_at=payload.expires_at,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/promocodes/{promo_id}/state")
async def web_admin_promo_state(
    promo_id: uuid.UUID,
    payload: PromoStateRequest,
    request: Request,
    context: AdminPromoWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPromoService.set_active(
            session,
            admin=context.account,
            promo_id=promo_id,
            is_active=payload.is_active,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/prompts")
async def web_admin_prompts(
    context: AdminPromptReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
) -> dict[str, Any]:
    return await AdminContentService.list_prompts(
        session,
        admin=context.account,
        status=status_filter,
    )


@router.post("/prompts/{prompt_id}/moderate")
async def web_admin_prompt_moderate(
    prompt_id: uuid.UUID,
    payload: PromptModerationRequest,
    request: Request,
    context: AdminPromptWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminContentService.moderate_prompt(
            session,
            admin=context.account,
            prompt_id=prompt_id,
            action=payload.action,
            reason=payload.reason,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/trends")
async def web_admin_trends(context: AdminSocialDep, session: SessionDep) -> dict[str, Any]:
    return await AdminContentService.list_trends(session, admin=context.account)


@router.post("/trends", status_code=status.HTTP_201_CREATED)
async def web_admin_trend_create(
    payload: TrendCreateRequest,
    request: Request,
    context: AdminSocialDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminContentService.create_trend(
            session,
            admin=context.account,
            title=payload.title,
            payload=payload.payload,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.delete("/trends/{trend_id}")
async def web_admin_trend_remove(
    trend_id: uuid.UUID,
    request: Request,
    context: AdminSocialDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminContentService.remove_trend(
            session,
            admin=context.account,
            trend_id=trend_id,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/feed/{generation_id}/moderation")
async def web_admin_feed_moderate(
    generation_id: uuid.UUID,
    payload: FeedModerationRequest,
    request: Request,
    context: AdminSocialDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminContentService.moderate_generation(
            session,
            admin=context.account,
            generation_id=generation_id,
            state=payload.state,
            reason=payload.reason,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/runtime")
async def web_admin_runtime(context: AdminRuntimeDep, session: SessionDep) -> dict[str, Any]:
    return await AdminRuntimeService.get_settings(session, admin=context.account)


@router.post("/runtime/subscription-required")
async def web_admin_subscription_required(
    payload: RuntimeSubscriptionRequest,
    request: Request,
    context: AdminRuntimeDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminRuntimeService.set_subscription_required(
            session,
            admin=context.account,
            enabled=payload.enabled,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/runtime/reload")
async def web_admin_runtime_reload(
    request: Request,
    context: AdminRuntimeDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminRuntimeService.reload_runtime_config(
            session,
            admin=context.account,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/partners/analytics")
async def web_admin_partner_analytics(
    context: AdminPartnerReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    return await AdminPartnerService.analytics(session, admin=context.account)


@router.get("/partners/withdrawals")
async def web_admin_partner_withdrawals(
    context: AdminPartnerReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    return await AdminPartnerService.list_withdrawals(
        session,
        admin=context.account,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post("/partners/withdrawals/{withdrawal_id}/state")
async def web_admin_partner_withdrawal_state(
    withdrawal_id: uuid.UUID,
    payload: WithdrawalStateRequest,
    request: Request,
    context: AdminPartnerWriteDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPartnerService.update_withdrawal(
            session,
            admin=context.account,
            withdrawal_id=withdrawal_id,
            status=payload.status,
            reason=payload.reason,
            idempotency_key=_require_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirmed(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        ),
    )
    return {**result, "idempotency_replayed": replayed}
