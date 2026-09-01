from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.core.config import settings
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.feed_links import mini_app_deep_link, trend_payload
from app.services.model_catalog import InvalidModelParametersError, SPECS, UnknownModelError
from app.services.trend_collections import TrendCollectionService
from app.services.trends import TrendRecipeError, TrendService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/trends", tags=["trends"])


class RunTrendRequest(BaseModel):
    reference_urls: list[str] = Field(default_factory=list, max_length=16)


class InlineTrendWriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AdminPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, InsufficientBalanceError):
        return HTTPException(status_code=409, detail="Insufficient credits")
    if isinstance(exc, (TrendRecipeError, UnknownModelError, InvalidModelParametersError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Trend operation failed")


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _command_key(value: str | None) -> str:
    key = str(value or "").strip() or f"inline-trend:{uuid.uuid4()}"
    if len(key) > 160:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return key


def _request_id(request: Request) -> str:
    value = str(request.headers.get("X-Request-Id") or "").strip()
    return value[:96] if value else f"mini-app:{uuid.uuid4()}"


async def _inline_admin(session: SessionDep, *, user_id: uuid.UUID) -> AdminAccount:
    account = await session.scalar(
        select(AdminAccount).where(
            AdminAccount.user_id == user_id,
            AdminAccount.is_active.is_(True),
        )
    )
    if account is None:
        raise HTTPException(status_code=403, detail="Admin access required")
    AdminPolicy.authorize_action(account, "social.moderate", confirmed=True)
    return account


async def _customer_price(
    session: SessionDep,
    *,
    user_id: uuid.UUID,
    item: dict[str, Any],
) -> dict[str, Any]:
    retail = Decimal(str(item.get("cost_credits") or "0"))
    decision = await BillingAccessService.decision(
        session,
        user_id=user_id,
        retail_cost=retail,
    )
    view = dict(item)
    view["retail_cost_credits"] = _amount(decision.retail_cost)
    view["retail_cost_rox"] = _amount(decision.retail_cost)
    view["admin_free"] = decision.admin_free
    view["cost_credits"] = _amount(decision.effective_cost)
    view["cost_rox"] = _amount(decision.effective_cost)
    view["cost_rub"] = _amount(InternalCreditService.rubles_for(decision.effective_cost))
    return view


@router.get("")
async def list_trends(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    media_type: Literal["image", "video"] | None = Query(default=None),
) -> dict[str, object]:
    try:
        payload = await TrendService.list_public(session, limit=limit, media_type=media_type)
        items = [
            await _customer_price(session, user_id=user.id, item=dict(item))
            for item in payload.get("items", [])
        ]
        return {**payload, "items": items}
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.get("/manage")
async def inline_admin_trend_list(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        await _inline_admin(session, user_id=user.id)
        rows = list(
            (
                await session.scalars(
                    select(AdminTrend).order_by(AdminTrend.created_at.desc())
                )
            ).all()
        )
        models = [spec.public_dict() for spec in SPECS if spec.media_type in {"image", "video"}]
        models.sort(key=lambda item: (str(item["media_type"]), str(item["family"]), str(item["title"])))
        return {
            "items": [TrendService.admin_view(item) for item in rows],
            "models": models,
            "limits": {"max_references": 16, "max_tags": 20},
        }
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/manage")
async def inline_admin_trend_create(
    payload: InlineTrendWriteRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)
        title = payload.title.strip()
        recipe = await TrendService.validate_recipe(session, title=title, payload=payload.payload)
        trend_id = uuid.uuid4()

        async def operation() -> dict[str, Any]:
            item = AdminTrend(
                id=trend_id,
                title=title,
                payload=recipe,
                is_active=payload.is_active,
                created_by_admin_id=account.id,
            )
            session.add(item)
            await session.flush()
            await TrendCollectionService.assign_from_tags(
                session,
                admin_id=account.id,
                trend_id=item.id,
                tags=recipe.get("tags") or [],
            )
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.create.inline", "title": title, "payload": recipe},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.patch("/manage/{trend_id}")
async def inline_admin_trend_update(
    trend_id: uuid.UUID,
    payload: InlineTrendWriteRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)
        title = payload.title.strip()
        recipe = await TrendService.validate_recipe(session, title=title, payload=payload.payload)

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
            await TrendCollectionService.assign_from_tags(
                session,
                admin_id=account.id,
                trend_id=item.id,
                tags=recipe.get("tags") or [],
            )
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.update.inline", "title": title, "payload": recipe, "is_active": payload.is_active},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.delete("/manage/{trend_id}")
async def inline_admin_trend_deactivate(
    trend_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)

        async def operation() -> dict[str, Any]:
            item = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update())
            if item is None:
                raise LookupError("Trend not found")
            item.is_active = False
            await session.flush()
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.deactivate.inline"},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/manage/{trend_id}/activate")
async def inline_admin_trend_activate(
    trend_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)

        async def operation() -> dict[str, Any]:
            item = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update())
            if item is None:
                raise LookupError("Trend not found")
            item.is_active = True
            await session.flush()
            return TrendService.admin_view(item)

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.activate.inline"},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.get("/{trend_id}")
async def get_trend(
    trend_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        item = await TrendService.get_public(session, trend_id=trend_id)
        return await _customer_price(session, user_id=user.id, item=item)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/{trend_id}/share")
async def share_trend(
    trend_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    """Return a canonical Telegram share link attributed to the current sharer."""

    try:
        item = await TrendService.get_public(session, trend_id=trend_id)
    except Exception as exc:
        raise _domain_error(exc) from exc

    title = str(item.get("title") if isinstance(item, dict) else getattr(item, "title", "Тренд"))
    payload = trend_payload(trend_id, user.telegram_id)
    base = str(settings.public_base_url or "").strip().rstrip("/")
    fallback_query = urlencode({"id": str(trend_id), "start_payload": payload, "startapp": payload})
    fallback = f"{base}/mini-app/trend/?{fallback_query}" if base else None
    link = mini_app_deep_link(payload, fallback_url=fallback)
    if not link:
        raise HTTPException(status_code=503, detail="Public Mini App link is not configured")

    share_text = f"Попробуй тренд «{title}» в ROXY ✨"
    share_url = f"https://t.me/share/url?{urlencode({'url': link, 'text': share_text})}"
    return {
        "id": str(trend_id),
        "link": link,
        "copy_link": link,
        "share_text": share_text,
        "share_url": share_url,
    }


@router.post("/{trend_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_trend(
    trend_id: uuid.UUID,
    payload: RunTrendRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    try:
        generation, trend_meta = await TrendService.run(
            session,
            redis,
            user_id=user.id,
            trend_id=trend_id,
            reference_urls=payload.reference_urls,
        )
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc

    params = generation.parameters or {}
    return {
        "id": str(generation.id),
        "task_id": str(generation.id),
        "status": generation.status,
        "cost_credits": format(generation.cost_rox, ".2f"),
        "cost_rox": format(generation.cost_rox, ".2f"),
        "cost_rub": format(InternalCreditService.rubles_for(generation.cost_rox), ".2f"),
        "retail_cost_rox": str(params.get("_retail_cost_rox") or generation.cost_rox),
        "admin_free": bool(params.get("_admin_free", False)),
        "result_url": generation.result_url,
        **trend_meta,
    }
