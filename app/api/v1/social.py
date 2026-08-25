from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Generation, User
from app.db.social_models import UserSubscription
from app.services.feed import FeedService
from app.services.social import (
    SelfSubscriptionError,
    SocialProfileNotFoundError,
    SocialService,
)

router = APIRouter(prefix="/social", tags=["social"])


async def _owned_generation_or_404(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
):  # type: ignore[no-untyped-def]
    generation = await SocialService.owned_generation(
        session,
        generation_id=generation_id,
        user_id=user.id,
    )
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


@router.get("/generations/{generation_id}")
async def generation_social_state(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation_or_404(generation_id, user, session)
    state = await SocialService.generation_like_state(
        session,
        generation_id=generation.id,
        viewer_user_id=user.id,
    )
    return {
        "generation_id": str(generation.id),
        "author_id": str(generation.user_id),
        **state,
    }


@router.post("/generations/{generation_id}/like")
async def like_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation_or_404(generation_id, user, session)
    result = await SocialService.like_generation(
        session,
        generation_id=generation.id,
        user_id=user.id,
    )
    await session.commit()
    return {"generation_id": str(generation.id), **result}


@router.delete("/generations/{generation_id}/like")
async def unlike_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation_or_404(generation_id, user, session)
    result = await SocialService.unlike_generation(
        session,
        generation_id=generation.id,
        user_id=user.id,
    )
    await session.commit()
    return {"generation_id": str(generation.id), **result}


@router.get("/profiles")
async def public_profile_by_username(
    user: CurrentUserDep,
    session: SessionDep,
    username: str = Query(min_length=1, max_length=64),
) -> dict[str, object]:
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        raise HTTPException(status_code=422, detail="Username is required")
    author = await session.scalar(
        select(User).where(func.lower(User.username) == normalized)
    )
    if author is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        return await SocialService.public_profile(
            session,
            author_user_id=author.id,
            viewer_user_id=user.id,
        )
    except SocialProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc


@router.get("/profiles/{author_id}")
async def public_profile(
    author_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        return await SocialService.public_profile(
            session,
            author_user_id=author_id,
            viewer_user_id=user.id,
        )
    except SocialProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc


@router.post("/profiles/{author_id}/subscribe")
async def subscribe(
    author_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        result = await SocialService.subscribe(
            session,
            author_user_id=author_id,
            subscriber_user_id=user.id,
        )
    except SocialProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc
    except SelfSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return result


@router.delete("/profiles/{author_id}/subscribe")
async def unsubscribe(
    author_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        result = await SocialService.unsubscribe(
            session,
            author_user_id=author_id,
            subscriber_user_id=user.id,
        )
    except SelfSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return result


@router.get("/subscriptions/feed")
async def subscriptions_feed(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=24, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    """Return one merged feed for authors followed by the current viewer.

    This mirrors the mature Banano Mini App contract: the frontend should not fan
    out to every followed profile just to build the subscriptions tab.
    """

    statement = (
        select(Generation)
        .join(UserSubscription, UserSubscription.author_user_id == Generation.user_id)
        .join(User, User.id == Generation.user_id)
        .where(
            UserSubscription.subscriber_user_id == user.id,
            Generation.status == "succeeded",
            Generation.is_profile_visible.is_(True),
            Generation.publication_scope.in_(("feed", "profile")),
            User.is_active.is_(True),
        )
        .order_by(
            Generation.feed_published_at.desc().nullslast(),
            Generation.created_at.desc(),
            Generation.id.desc(),
        )
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list((await session.scalars(statement)).all())
    page = rows[:limit]
    cards = await FeedService.cards_for_generations(
        session,
        page,
        viewer_user_id=user.id,
        surface="profile",
    )
    return {
        "items": cards,
        "limit": limit,
        "offset": offset,
        "has_more": len(rows) > limit,
    }


@router.get("/subscriptions")
async def subscriptions(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    items = await SocialService.subscriptions(
        session,
        subscriber_user_id=user.id,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}
