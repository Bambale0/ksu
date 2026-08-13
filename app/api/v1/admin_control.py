from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.services.admin_exports import AdminExportService
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.admin_payments import AdminPaymentService
from app.services.admin_policy import AdminPolicyError
from app.services.admin_promos import AdminPromoService
from app.services.admin_reporting import AdminReportingService
from app.services.admin_security import AdminAuthService
from app.services.admin_support import AdminSupportService
from app.services.admin_users import AdminUserService

router = APIRouter(prefix="/admin/control", tags=["admin-control"])

UsersReadDep = Annotated[AdminContext, Depends(require_permission("users.read"))]
UsersManageDep = Annotated[AdminContext, Depends(require_permission("users.manage"))]
WalletManageDep = Annotated[
    AdminContext,
    Depends(require_permission("users.wallet.adjust", step_up=True)),
]
PaymentsReadDep = Annotated[AdminContext, Depends(require_permission("payments.read"))]
PaymentsManageDep = Annotated[
    AdminContext,
    Depends(require_permission("payments.manage", step_up=True)),
]
OperationsReadDep = Annotated[AdminContext, Depends(require_permission("operations.read"))]
OperationsManageDep = Annotated[
    AdminContext,
    Depends(require_permission("operations.manage", step_up=True)),
]
SupportReadDep = Annotated[AdminContext, Depends(require_permission("support.read"))]
SupportManageDep = Annotated[AdminContext, Depends(require_permission("support.manage"))]
PromosReadDep = Annotated[AdminContext, Depends(require_permission("promocodes.read"))]
PromosManageDep = Annotated[AdminContext, Depends(require_permission("promocodes.manage"))]
FinanceReadDep = Annotated[AdminContext, Depends(require_permission("finance.read"))]


class UserReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class BalanceRequest(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=5, max_length=500)


class RefundRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SupportAssignRequest(BaseModel):
    assigned_admin_id: uuid.UUID | None = None


class SupportUpdateRequest(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None


class SupportReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    reward_credits: Decimal = Field(gt=0, le=100_000)
    max_uses: int | None = Field(default=None, ge=1, le=10_000_000)


def _confirm(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "confirm", "confirmed"}


def _idempotency(value: str | None) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 160:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key is required")
    return key


def _request_id(request: Request) -> str:
    value = str(request.headers.get("X-Request-Id") or "").strip()
    return value[:96] if value else f"web-control:{uuid.uuid4()}"


def _error(exc: Exception) -> HTTPException:
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
        raise _error(exc) from exc


@router.get("/users")
async def control_users(
    context: UsersReadDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=128),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    return await AdminUserService.list_users(
        session,
        admin=context.account,
        q=q,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}")
async def control_user(
    user_id: uuid.UUID,
    context: UsersReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminUserService.get_user(session, admin=context.account, user_id=user_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/users/{user_id}/block")
async def control_user_block(
    user_id: uuid.UUID,
    payload: UserReasonRequest,
    request: Request,
    context: UsersManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminUserService.set_blocked(
            session,
            admin=context.account,
            user_id=user_id,
            blocked=True,
            reason=payload.reason,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/users/{user_id}/unblock")
async def control_user_unblock(
    user_id: uuid.UUID,
    payload: UserReasonRequest,
    request: Request,
    context: UsersManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminUserService.set_blocked(
            session,
            admin=context.account,
            user_id=user_id,
            blocked=False,
            reason=payload.reason,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/users/{user_id}/balance")
async def control_user_balance(
    user_id: uuid.UUID,
    payload: BalanceRequest,
    request: Request,
    context: WalletManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminUserService.adjust_balance(
            session,
            admin=context.account,
            user_id=user_id,
            amount=payload.amount,
            reason=payload.reason,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/payments")
async def control_payments(
    context: PaymentsReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    provider: str | None = Query(default=None, max_length=64),
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    return await AdminReportingService.payments(
        session,
        admin=context.account,
        status=status_filter,
        provider=provider,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.post("/payments/{payment_id}/recheck")
async def control_payment_recheck(
    payment_id: uuid.UUID,
    request: Request,
    context: PaymentsReadDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPaymentService.recheck(
            session,
            admin=context.account,
            payment_id=payment_id,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/payments/{payment_id}/reprocess")
async def control_payment_reprocess(
    payment_id: uuid.UUID,
    request: Request,
    context: PaymentsManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminPaymentService.reprocess(
            session,
            admin=context.account,
            payment_id=payment_id,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/operations")
async def control_operations(
    context: OperationsReadDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    return await AdminGenerationOperationService.list_operations(
        session,
        admin=context.account,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/operations/{operation_id}")
async def control_operation(
    operation_id: uuid.UUID,
    context: OperationsReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminGenerationOperationService.get_operation(
            session,
            admin=context.account,
            operation_id=operation_id,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/operations/{operation_id}/replay")
async def control_operation_replay(
    operation_id: uuid.UUID,
    request: Request,
    context: OperationsManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminGenerationOperationService.replay_operation(
            session,
            admin=context.account,
            operation_id=operation_id,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/operations/{operation_id}/refund")
async def control_operation_refund(
    operation_id: uuid.UUID,
    payload: RefundRequest,
    request: Request,
    context: OperationsManageDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    result, replayed = await _commit(
        session,
        AdminGenerationOperationService.refund_operation(
            session,
            admin=context.account,
            operation_id=operation_id,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            step_up_valid=AdminAuthService.step_up_valid(context.session),
            reason=payload.reason,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/tickets")
async def control_tickets(
    context: SupportReadDep,
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


@router.get("/tickets/{ticket_id}")
async def control_ticket(
    ticket_id: uuid.UUID,
    context: SupportReadDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        return await AdminSupportService.get_ticket(
            session,
            admin=context.account,
            ticket_id=ticket_id,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/tickets/{ticket_id}/assign")
async def control_ticket_assign(
    ticket_id: uuid.UUID,
    payload: SupportAssignRequest,
    request: Request,
    context: SupportManageDep,
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
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/tickets/{ticket_id}/update")
async def control_ticket_update(
    ticket_id: uuid.UUID,
    payload: SupportUpdateRequest,
    request: Request,
    context: SupportManageDep,
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
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.post("/tickets/{ticket_id}/reply")
async def control_ticket_reply(
    ticket_id: uuid.UUID,
    payload: SupportReplyRequest,
    request: Request,
    context: SupportManageDep,
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
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
            request=request,
            admin_session=context.session,
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/promocodes")
async def control_promocodes(
    context: PromosReadDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    if q:
        try:
            return {"item": await AdminPromoService.lookup(session, admin=context.account, query=q)}
        except Exception as exc:
            raise _error(exc) from exc
    return await AdminPromoService.list_promos(session, admin=context.account)


@router.post("/promocodes")
async def control_promocode_create(
    payload: PromoCreateRequest,
    request: Request,
    context: PromosManageDep,
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
            expires_at=None,
            idempotency_key=_idempotency(idempotency_key),
            request_id=_request_id(request),
            confirmed=_confirm(confirmation),
        ),
    )
    return {**result, "idempotency_replayed": replayed}


@router.get("/exports/{kind}.{format_name}")
async def control_export(
    kind: Literal["payments", "withdrawals"],
    format_name: Literal["csv", "xlsx"],
    context: FinanceReadDep,
    session: SessionDep,
) -> Response:
    filename, content_type, content = await AdminExportService.export(
        session,
        admin=context.account,
        kind=kind,
        format=format_name,
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
