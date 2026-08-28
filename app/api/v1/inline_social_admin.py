from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount, Generation
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_content import AdminContentService
from app.services.admin_policy import AdminPolicy, AdminPolicyError

router = APIRouter(prefix="/inline-admin", tags=["inline-social-admin"])


class FeedModerationRequest(BaseModel):
    action: Literal["visible", "blurred", "hidden", "removed"]
    reason: str = Field(default="Модерация из ленты ROXY", min_length=3, max_length=1000)


def _command_key(value: str | None, prefix: str) -> str:
    key = str(value or "").strip() or f"{prefix}:{uuid.uuid4()}"
    if len(key) > 160:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return key


def _request_id(request: Request) -> str:
    value = str(request.headers.get("X-Request-Id") or "").strip()
    return value[:96] if value else f"mini-app-admin:{uuid.uuid4()}"


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


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AdminPolicyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.post("/feed/{generation_id}/moderation")
async def inline_feed_moderation(
    generation_id: uuid.UUID,
    payload: FeedModerationRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    try:
        account = await _inline_admin(session, user_id=user.id)
        moderation_state = "removed" if payload.action in {"hidden", "removed"} else payload.action
        result, replayed = await AdminContentService.moderate_generation(
            session,
            admin=account,
            generation_id=generation_id,
            state=moderation_state,  # type: ignore[arg-type]
            reason=payload.reason,
            idempotency_key=_command_key(idempotency_key, "feed-moderate"),
            request_id=_request_id(request),
            confirmed=True,
        )

        if payload.action == "removed" and not replayed:
            generation = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
            if generation is None:
                raise LookupError("Generation not found")
            generation.publication_scope = "private"
            generation.is_public_feed = False
            generation.is_profile_visible = False
            generation.feed_prompt_visible = False
            generation.feed_references_visible = False
            await session.flush()

        await session.commit()
        return {
            **result,
            "action": payload.action,
            "idempotency_replayed": replayed,
        }
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.delete("/trends/{trend_id}")
async def inline_trend_delete(
    trend_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    try:
        account = await _inline_admin(session, user_id=user.id)

        async def operation() -> dict[str, object]:
            item = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()
            )
            if item is None:
                raise LookupError("Trend not found")
            await session.delete(item)
            await session.flush()
            return {"id": str(trend_id), "deleted": True}

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=_command_key(idempotency_key, "trend-delete"),
            admin_user_id=account.id,
            request_id=_request_id(request),
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"operation": "trend.delete.inline"},
            operation=operation,
        )
        await session.commit()
        return {**result, "idempotency_replayed": replayed}
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc
