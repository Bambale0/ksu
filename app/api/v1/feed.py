from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.models import Generation, User
from app.services import action_telemetry
from app.services.feed import (
    FeedDerivativePublicationError,
    FeedError,
    FeedMediaUnavailableError,
    FeedNotFoundError,
    FeedPublicationError,
    FeedService,
)
from app.services.feed_links import mini_app_deep_link
from app.services.wallet import InsufficientBalanceError

router = APIRouter(tags=["feed"])


class PublishRequest(BaseModel):
    publication_scope: Literal["profile", "feed"]
    prompt_visible: bool = False
    references_visible: bool = False


class RemoveRequest(BaseModel):
    target_scope: Literal["private", "profile"] = "private"


class SurfaceRequest(BaseModel):
    surface: Literal["feed", "profile"] = "feed"


class CommentRequest(BaseModel):
    surface: Literal["feed", "profile"]
    text: str = Field(min_length=1, max_length=300)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FeedNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, FeedDerivativePublicationError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FeedMediaUnavailableError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FeedPublicationError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FeedError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Feed operation failed")


def _direct_mini_app_link(link: str | None) -> str | None:
    """Turn a verified bot start payload into a direct Main Mini App link."""

    if not link:
        return None
    parsed = urlparse(link)
    payload = (parse_qs(parsed.query).get("start") or parse_qs(parsed.query).get("startapp") or [""])[0]
    if payload:
        return mini_app_deep_link(payload)
    return link


def _sanitize_trend_card(card: dict[str, object], generation: Generation) -> dict[str, object]:
    if generation.action_type != "trend":
        return card
    card = dict(card)
    card["prompt"] = ""
    card["prompt_hidden"] = True
    card["prompt_actions_allowed"] = False
    card["feed_prompt_visible"] = False
    card["reference_images"] = []
    card["reference_videos"] = []
    card["references_hidden"] = True
    card["feed_references_visible"] = False
    return card


@router.get("/feed")
async def feed(
    user: CurrentUserDep,
    session: SessionDep,
    sort: Literal["recent", "top_day", "top"] = Query(default="recent"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    rows = await FeedService.get_feed_generations(session, sort=sort, limit=limit, offset=offset)
    cards = await FeedService.cards_for_generations(
        session, rows, viewer_user_id=user.id, surface="feed"
    )
    by_id = {str(row.id): row for row in rows}
    cards = [
        _sanitize_trend_card(card, by_id[str(card["id"])])
        if str(card.get("id")) in by_id
        else card
        for card in cards
    ]
    return {"items": cards, "sort": sort, "limit": limit, "offset": offset}


@router.get("/feed/{generation_id}")
async def feed_item(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    surface: Literal["feed", "profile"] = Query(default="feed"),
) -> dict[str, object]:
    try:
        generation = await FeedService.assert_surface_visible(session, generation_id, surface=surface)
        if surface == "feed":
            card = await FeedService.get_feed_generation_card(
                session, generation_id=generation_id, viewer_user_id=user.id
            )
        else:
            card = await FeedService.get_profile_generation_card(
                session, generation_id=generation_id, viewer_user_id=user.id
            )
        return _sanitize_trend_card(card, generation)
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc


@router.get("/profiles/{referral_code}/feed")
async def profile_feed(
    referral_code: str,
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    try:
        author = await FeedService.author_by_referral_code(session, referral_code)
        rows = await FeedService.get_user_feed_generations(
            session, author_user_id=author.id, profile_visible_only=True, limit=limit, offset=offset
        )
        cards = await FeedService.cards_for_generations(
            session, rows, viewer_user_id=user.id, surface="profile"
        )
        by_id = {str(row.id): row for row in rows}
        cards = [
            _sanitize_trend_card(card, by_id[str(card["id"])])
            if str(card.get("id")) in by_id
            else card
            for card in cards
        ]
    except FeedNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "author": {
            "id": str(author.id),
            "telegram_id": author.telegram_id,
            "username": author.username,
            "display_name": author.first_name or author.username or "Пользователь ROXY",
            "referral_code": str(author.telegram_id),
        },
        "items": cards,
        "limit": limit,
        "offset": offset,
    }


@router.post("/feed/{generation_id}/publish")
async def publish(
    generation_id: uuid.UUID,
    payload: PublishRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        source = await session.get(Generation, generation_id)
        trend_owned = bool(source and source.user_id == user.id and source.action_type == "trend")
        generation = await FeedService.share_to_feed(
            session,
            generation_id=generation_id,
            owner_user_id=user.id,
            publication_scope=payload.publication_scope,
            prompt_visible=False if trend_owned else payload.prompt_visible,
            references_visible=False if trend_owned else payload.references_visible,
        )
        await session.commit()
        surface = "feed" if generation.publication_scope == "feed" else "profile"
        card = await FeedService.to_card(
            session, generation, viewer_user_id=user.id, surface=surface
        )
        card = _sanitize_trend_card(card, generation)
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    action_telemetry.track(
        action_telemetry.PUBLISH_SUCCESS,
        user_id=user.id,
        generation_id=str(generation.id),
        publication_scope=generation.publication_scope,
    )
    return {
        "publication_scope": generation.publication_scope,
        "downgraded_to_profile": (
            payload.publication_scope == "feed" and generation.publication_scope == "profile"
        ),
        "item": card,
        "share": FeedService.share_payload(generation, user.telegram_id),
    }


@router.post("/feed/{generation_id}/remove")
async def remove(
    generation_id: uuid.UUID,
    payload: RemoveRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        generation = await FeedService.remove_from_feed(
            session,
            generation_id=generation_id,
            owner_user_id=user.id,
            target_scope=payload.target_scope,
        )
        await session.commit()
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {
        "id": str(generation.id),
        "publication_scope": generation.publication_scope,
        "is_public_feed": generation.is_public_feed,
        "is_profile_visible": generation.is_profile_visible,
    }


@router.post("/feed/{generation_id}/like")
async def like(
    generation_id: uuid.UUID,
    payload: SurfaceRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        result = await FeedService.like_feed_generation(
            session, generation_id=generation_id, user_id=user.id, surface=payload.surface
        )
        await session.commit()
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {"id": str(generation_id), "surface": payload.surface, **result}


@router.delete("/feed/{generation_id}/like")
async def unlike(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    surface: Literal["feed", "profile"] = Query(default="feed"),
) -> dict[str, object]:
    try:
        result = await FeedService.unlike_feed_generation(
            session, generation_id=generation_id, user_id=user.id, surface=surface
        )
        await session.commit()
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {"id": str(generation_id), "surface": surface, **result}


@router.post("/feed/{generation_id}/share")
async def share(
    generation_id: uuid.UUID,
    payload: SurfaceRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        generation = await FeedService.assert_surface_visible(
            session, generation_id, surface=payload.surface
        )
        shares_count = await FeedService.increment_feed_share(
            session, generation_id=generation_id, surface=payload.surface
        )
        author = await session.get(User, generation.user_id)
        if author is None:
            raise FeedNotFoundError("Publication author not found")
        link = _direct_mini_app_link(
            FeedService.post_deep_link(generation.id, str(author.telegram_id))
        )
        await session.commit()
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    action_telemetry.track(
        action_telemetry.SHARE_CLICKED,
        user_id=user.id,
        generation_id=str(generation_id),
        surface=payload.surface,
    )
    return {
        "id": str(generation_id),
        "shares_count": shares_count,
        "link": link,
        "share": FeedService.share_payload(generation, author.telegram_id),
    }


@router.get("/feed/{generation_id}/comments")
async def comments(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    surface: Literal["feed", "profile"] = Query(default="feed"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    del user
    try:
        items = await FeedService.get_feed_comments(
            session, generation_id=generation_id, surface=surface, limit=limit, offset=offset
        )
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {"items": items, "surface": surface, "limit": limit, "offset": offset}


@router.post("/feed/{generation_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    generation_id: uuid.UUID,
    payload: CommentRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        comment = await FeedService.add_feed_comment(
            session,
            generation_id=generation_id,
            user_id=user.id,
            surface=payload.surface,
            text=payload.text,
        )
        await session.commit()
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {
        "id": str(comment.id),
        "generation_id": str(comment.generation_id),
        "surface": comment.surface,
        "text": comment.text,
        "created_at": comment.created_at.isoformat(),
    }


@router.post("/feed/{generation_id}/remix", status_code=status.HTTP_202_ACCEPTED)
async def remix(
    generation_id: uuid.UUID,
    payload: SurfaceRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    try:
        source = await FeedService.assert_surface_visible(
            session, generation_id, surface=payload.surface
        )
        if source.action_type == "trend":
            raise FeedError("Trend generations cannot be remixed")
        generation = await FeedService.remix(
            session,
            redis,
            source_generation_id=generation_id,
            remix_author_id=user.id,
            surface=payload.surface,
        )
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient credits") from exc
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    return {
        "id": str(generation.id),
        "status": generation.status,
        "source_feed_gen_id": str(generation.source_feed_gen_id),
        "action_type": generation.action_type,
    }


@router.get("/feed/{generation_id}/link")
async def link(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    kind: Literal["post", "remix"] = Query(default="post"),
    surface: Literal["feed", "profile"] = Query(default="feed"),
) -> dict[str, object]:
    del user
    try:
        generation = await FeedService.assert_surface_visible(
            session, generation_id, surface=surface
        )
        author = await session.get(User, generation.user_id)
        if author is None:
            raise FeedNotFoundError("Publication author not found")
    except (FeedError, FeedNotFoundError) as exc:
        raise _http_error(exc) from exc
    referral_code = str(author.telegram_id)
    value = (
        _direct_mini_app_link(FeedService.post_deep_link(generation.id, referral_code))
        if kind == "post"
        else FeedService.remix_deep_link(generation.id, referral_code)
    )
    return {"kind": kind, "surface": surface, "link": value}


@router.get("/profiles/{referral_code}/link")
async def profile_link(
    referral_code: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    del user
    try:
        author = await FeedService.author_by_referral_code(session, referral_code)
    except FeedNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "author_id": str(author.id),
        "link": FeedService.profile_deep_link(str(author.telegram_id)),
    }
