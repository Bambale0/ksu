from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.trend_collections import TrendCollectionError, TrendCollectionService
from app.services.trends import TrendService

router = APIRouter(prefix="/trend-collections", tags=["trend-collections"])


class CollectionWriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    sort_order: int = Field(default=100, ge=-100_000, le=100_000)
    is_active: bool = True


class CollectionAssignmentRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=64)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _command_key(value: str | None, prefix: str) -> str:
    key = str(value or "").strip() or f"{prefix}:{uuid.uuid4()}"
    if len(key) > 160:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return key


def _request_id(request: Request) -> str:
    value = str(request.headers.get("X-Request-Id") or "").strip()
    return value[:96] if value else f"mini-app:{uuid.uuid4()}"


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AdminPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (TrendCollectionError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Template folder operation failed")


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
    decision = await BillingAccessService.decision(session, user_id=user_id, retail_cost=retail)
    view = dict(item)
    view["retail_cost_credits"] = _amount(decision.retail_cost)
    view["retail_cost_rox"] = _amount(decision.retail_cost)
    view["admin_free"] = decision.admin_free
    view["cost_credits"] = _amount(decision.effective_cost)
    view["cost_rox"] = _amount(decision.effective_cost)
    view["cost_rub"] = _amount(InternalCreditService.rubles_for(decision.effective_cost))
    return view


@router.get("")
async def list_trend_collections(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    del user
    state = await TrendCollectionService.state(session)
    collections = [dict(item) for item in state["collections"] if item.get("is_active")]
    by_id = {item["id"]: item for item in collections}
    for item in collections:
        item.update({"item_count": 0, "photo_count": 0, "video_count": 0, "preview_url": None})

    rows = list(
        (
            await session.scalars(
                select(AdminTrend)
                .where(AdminTrend.is_active.is_(True))
                .order_by(AdminTrend.created_at.desc())
            )
        ).all()
    )
    for trend in rows:
        collection_id = TrendCollectionService.assigned_collection(state, trend.id)
        collection = by_id.get(collection_id)
        if collection is None:
            continue
        payload = trend.payload if isinstance(trend.payload, dict) else {}
        media_type = str(payload.get("media_type") or "").lower()
        if media_type not in {"image", "video"}:
            continue
        collection["item_count"] += 1
        collection["photo_count" if media_type == "image" else "video_count"] += 1
        if not collection["preview_url"]:
            collection["preview_url"] = payload.get("preview_url")

    return {"items": collections}


@router.get("/manage")
async def manage_trend_collections(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        await _inline_admin(session, user_id=user.id)
        return await TrendCollectionService.state(session)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/manage")
async def create_trend_collection(
    payload: CollectionWriteRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)
        collection_id = f"folder-{uuid.uuid4().hex[:12]}"

        async def operation() -> dict[str, Any]:
            return await TrendCollectionService.upsert_collection(
                session,
                admin_id=account.id,
                collection_id=collection_id,
                payload=payload.model_dump(),
            )

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key, "folder-create"),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=collection_id,
            request_payload={"operation": "trend_collection.create", **payload.model_dump()},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.patch("/manage/{collection_id}")
async def update_trend_collection(
    collection_id: str,
    payload: CollectionWriteRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)
        state = await TrendCollectionService.state(session)
        if not any(item["id"] == collection_id for item in state["collections"]):
            raise LookupError("Folder not found")

        async def operation() -> dict[str, Any]:
            return await TrendCollectionService.upsert_collection(
                session,
                admin_id=account.id,
                collection_id=collection_id,
                payload=payload.model_dump(),
            )

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key, "folder-update"),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=collection_id,
            request_payload={"operation": "trend_collection.update", **payload.model_dump()},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


async def _set_collection_active(
    collection_id: str,
    *,
    active: bool,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: str | None,
) -> dict[str, Any]:
    account = await _inline_admin(session, user_id=user.id)

    async def operation() -> dict[str, Any]:
        return await TrendCollectionService.set_collection_active(
            session,
            admin_id=account.id,
            collection_id=collection_id,
            active=active,
        )

    result, replayed = await AdminCommandLedger.execute(
        session,
        idempotency_key=_command_key(idempotency_key, "folder-visibility"),
        admin_user_id=account.id,
        request_id=_request_id(request),
        action="social.moderate",
        target_id=collection_id,
        request_payload={"operation": "trend_collection.visibility", "active": active},
        operation=operation,
    )
    await session.commit()
    return {**result, "idempotency_replayed": replayed}


@router.delete("/manage/{collection_id}")
async def hide_trend_collection(
    collection_id: str,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        return await _set_collection_active(
            collection_id,
            active=False,
            request=request,
            user=user,
            session=session,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.post("/manage/{collection_id}/activate")
async def activate_trend_collection(
    collection_id: str,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        return await _set_collection_active(
            collection_id,
            active=True,
            request=request,
            user=user,
            session=session,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.put("/manage/items/{trend_id}")
async def assign_trend_collection(
    trend_id: uuid.UUID,
    payload: CollectionAssignmentRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        account = await _inline_admin(session, user_id=user.id)

        async def operation() -> dict[str, Any]:
            return await TrendCollectionService.assign_trend(
                session,
                admin_id=account.id,
                trend_id=trend_id,
                collection_id=payload.collection_id,
            )

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key, "folder-assign"),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={
                "operation": "trend_collection.assign",
                "collection_id": payload.collection_id,
            },
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.get("/{collection_id}/items")
async def list_collection_items(
    collection_id: str,
    user: CurrentUserDep,
    session: SessionDep,
    media_type: Literal["image", "video"] | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=100),
) -> dict[str, Any]:
    try:
        state = await TrendCollectionService.state(session)
        collection = next(
            (
                item
                for item in state["collections"]
                if item["id"] == collection_id and item.get("is_active")
            ),
            None,
        )
        if collection is None:
            raise LookupError("Folder not found")
        rows = list(
            (
                await session.scalars(
                    select(AdminTrend)
                    .where(AdminTrend.is_active.is_(True))
                    .order_by(AdminTrend.created_at.desc())
                )
            ).all()
        )
        items: list[dict[str, Any]] = []
        for trend in rows:
            if TrendCollectionService.assigned_collection(state, trend.id) != collection_id:
                continue
            try:
                view = await TrendService.public_view(session, trend)
            except (ValueError, KeyError):
                continue
            if media_type and view.get("media_type") != media_type:
                continue
            view["collection_id"] = collection_id
            items.append(await _customer_price(session, user_id=user.id, item=view))
        items.sort(key=lambda item: (int(item.get("sort_order", 0)), str(item.get("created_at", ""))), reverse=True)
        return {"collection": collection, "items": items[:limit]}
    except Exception as exc:
        raise _domain_error(exc) from exc
