from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Notification
from app.services.generation_progress import GENERATION_PROGRESS_KIND
from app.services.neironych_balance_alerts import BALANCE_NOTIFICATION_KINDS, NeironychBalanceAlertService

router = APIRouter(prefix="/notifications", tags=["notifications"])

_SENSITIVE_BALANCE_KINDS = BALANCE_NOTIFICATION_KINDS


async def _can_read_provider_balance(session: SessionDep, user: CurrentUserDep) -> bool:
    return await NeironychBalanceAlertService.authorized_owner(session, user.id)



def _view(item: Notification) -> dict[str, object]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "title": item.title,
        "body": item.body,
        "is_read": item.is_read,
        "created_at": item.created_at.isoformat(),
    }


@router.get("")
async def list_notifications(
    user: CurrentUserDep,
    session: SessionDep,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    statement = select(Notification).where(
        Notification.user_id == user.id,
        Notification.kind != GENERATION_PROGRESS_KIND,
    )
    can_read_balance = await _can_read_provider_balance(session, user)
    if not can_read_balance:
        statement = statement.where(Notification.kind.not_in(_SENSITIVE_BALANCE_KINDS))
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))
    rows = list(
        (
            await session.scalars(
                statement.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    unread_count = int(
        (
            await session.scalar(
                select(func.count()).select_from(Notification).where(
                    Notification.user_id == user.id,
                    Notification.kind != GENERATION_PROGRESS_KIND,
                    Notification.is_read.is_(False),
                    *([] if can_read_balance else [Notification.kind.not_in(_SENSITIVE_BALANCE_KINDS)]),
                )
            )
        )
        or 0
    )
    return {
        "items": [_view(item) for item in rows],
        "unread_count": unread_count,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, bool]:
    item = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.kind != GENERATION_PROGRESS_KIND,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if item.kind in _SENSITIVE_BALANCE_KINDS and not await _can_read_provider_balance(session, user):
        raise HTTPException(status_code=404, detail="Notification not found")
    if not item.is_read:
        item.is_read = True
        await session.commit()
    return {"is_read": True}


@router.post("/read-all")
async def mark_all_notifications_read(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, int]:
    can_read_balance = await _can_read_provider_balance(session, user)
    stmt = update(Notification).where(
        Notification.user_id == user.id,
        Notification.kind != GENERATION_PROGRESS_KIND,
        Notification.is_read.is_(False),
    )
    if not can_read_balance:
        stmt = stmt.where(Notification.kind.not_in(_SENSITIVE_BALANCE_KINDS))
    result = await session.execute(stmt.values(is_read=True))
    await session.commit()
    return {"updated": int(result.rowcount or 0)}
