from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
    statement = select(Notification).where(Notification.user_id == user.id)
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
                    Notification.is_read.is_(False),
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
        )
    )
    if item is None:
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
    result = await session.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await session.commit()
    return {"updated": int(result.rowcount or 0)}
