from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.admin_deps import AdminContext, require_permission
from app.api.deps import SessionDep
from app.db.admin_models import AdminTrend
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.model_catalog import SPECS
from app.services.trends import TrendService

router = APIRouter(prefix="/admin/trends", tags=["admin-trends"])

AdminSocialDep = Annotated[
    AdminContext,
    Depends(require_permission("social.moderate")),
]


class TrendUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


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


@router.get("/options")
async def web_admin_trend_options(context: AdminSocialDep) -> dict[str, Any]:
    del context
    models = [spec.public_dict() for spec in SPECS if spec.media_type in {"image", "video"}]
    models.sort(key=lambda item: (str(item["media_type"]), str(item["family"]), str(item["title"])))
    return {
        "models": models,
        "input_modes": ["none", "image"],
        "limits": {"max_references": 16, "max_tags": 20},
    }


@router.patch("/{trend_id}")
async def web_admin_trend_update(
    trend_id: uuid.UUID,
    payload: TrendUpdateRequest,
    request: Request,
    context: AdminSocialDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    try:
        AdminPolicy.authorize_action(
            context.account,
            "social.moderate",
            confirmed=_confirmed(confirmation),
        )
        title = payload.title.strip()
        recipe = await TrendService.validate_recipe(
            session,
            title=title,
            payload=payload.payload,
        )

        async def operation() -> dict[str, Any]:
            item = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()
            )
            if item is None:
                raise LookupError("Trend not found")
            item.title = title
            item.payload = recipe
            item.is_active = payload.is_active
            await session.flush()
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_require_idempotency(idempotency_key),
            admin_user_id=context.account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={
                "operation": "trend.update",
                "title": title,
                "payload": recipe,
                "is_active": payload.is_active,
            },
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/{trend_id}/activate")
async def web_admin_trend_activate(
    trend_id: uuid.UUID,
    request: Request,
    context: AdminSocialDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    confirmation: Annotated[str | None, Header(alias="X-Admin-Confirm")] = None,
) -> dict[str, Any]:
    try:
        AdminPolicy.authorize_action(
            context.account,
            "social.moderate",
            confirmed=_confirmed(confirmation),
        )

        async def operation() -> dict[str, Any]:
            item = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()
            )
            if item is None:
                raise LookupError("Trend not found")
            item.is_active = True
            await session.flush()
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_require_idempotency(idempotency_key),
            admin_user_id=context.account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.activate"},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc
