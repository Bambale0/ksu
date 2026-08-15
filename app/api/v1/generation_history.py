from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, or_, select

from app.api.deps import CurrentUserDep, SessionDep
from app.api.v1.generations import _generation_view, _owned_media_views
from app.db.history_models import GenerationHistoryState
from app.db.models import Generation

router = APIRouter(prefix="/generation-history", tags=["generation-history"])


@router.get("/hidden")
async def hidden_generations(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=50),
    before: uuid.UUID | None = Query(default=None),
) -> dict[str, object]:
    statement = (
        select(Generation)
        .join(
            GenerationHistoryState,
            and_(
                GenerationHistoryState.generation_id == Generation.id,
                GenerationHistoryState.user_id == user.id,
            ),
        )
        .where(
            Generation.user_id == user.id,
            GenerationHistoryState.hidden_at.is_not(None),
        )
    )

    if before is not None:
        anchor = await session.get(Generation, before)
        anchor_state = await session.get(GenerationHistoryState, before)
        if (
            anchor is None
            or anchor.user_id != user.id
            or anchor_state is None
            or anchor_state.user_id != user.id
            or anchor_state.hidden_at is None
        ):
            raise HTTPException(status_code=404, detail="Hidden history cursor not found")
        statement = statement.where(
            or_(
                Generation.created_at < anchor.created_at,
                and_(Generation.created_at == anchor.created_at, Generation.id < anchor.id),
            )
        )

    rows = list(
        (
            await session.scalars(
                statement.order_by(Generation.created_at.desc(), Generation.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    media = await _owned_media_views(session, user_id=user.id, generations=page)
    return {
        "items": [
            _generation_view(row, hidden=True, owned_media=media.get(row.id, []))
            for row in page
        ],
        "has_more": has_more,
        "next_before": str(page[-1].id) if has_more and page else None,
    }
