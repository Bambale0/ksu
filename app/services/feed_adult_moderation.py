from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_content_models import GenerationModerationState
from app.db.feed_models import FeedRemixEvent
from app.db.models import AdminAccount, Generation, User
from app.db.social_models import GenerationLike
from app.services.admin_policy import AdminPolicy

_PUBLIC_STATES = frozenset({"visible", "blurred"})
_HIDDEN_STATES = frozenset({"pending", "removed"})
_INSTALLED = False


def _blur_marker(value: str | None) -> str | None:
    if not value or "roxy_blur=1" in value:
        return value
    return f"{value}{'&' if '?' in value else '?'}roxy_blur=1"


class FeedAdultModerationService:
    """Creator 18+ declarations and the admin moderation queue.

    A creator declaration is intentionally not an admin decision. It creates a
    ``pending`` state with no admin actor. Only ``visible`` and ``blurred`` are
    public states; ``pending`` and ``removed`` are fail-closed.
    """

    @staticmethod
    async def list_admin_queue(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        state: str | None = "pending",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "social.moderate")
        if state is not None and state not in {"pending", "visible", "blurred", "removed"}:
            raise ValueError("Unknown feed moderation state")
        limit = max(1, min(limit, 200))
        offset = max(0, min(offset, 100_000))
        conditions = [
            Generation.is_adult_content.is_(True),
            Generation.publication_scope == "feed",
        ]
        if state is not None:
            conditions.append(GenerationModerationState.state == state)
        stmt = (
            select(Generation, GenerationModerationState, User)
            .join(
                GenerationModerationState,
                GenerationModerationState.generation_id == Generation.id,
            )
            .join(User, User.id == Generation.user_id)
            .where(*conditions)
            .order_by(
                GenerationModerationState.created_at.asc(),
                Generation.created_at.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        count_stmt = (
            select(func.count())
            .select_from(GenerationModerationState)
            .join(Generation, Generation.id == GenerationModerationState.generation_id)
            .where(*conditions)
        )
        rows = (await session.execute(stmt)).all()
        total = int((await session.scalar(count_stmt)) or 0)
        items: list[dict[str, Any]] = []
        for generation, moderation, author in rows:
            items.append(
                {
                    "generation_id": str(generation.id),
                    "state": moderation.state,
                    "reason": moderation.reason,
                    "adult_content": True,
                    "kind": generation.kind,
                    "model_id": str((generation.parameters or {}).get("_model_id") or "") or None,
                    "prompt": generation.prompt[:2000],
                    "result_url": generation.result_url,
                    "created_at": generation.created_at.isoformat(),
                    "queued_at": moderation.created_at.isoformat(),
                    "moderated_at": moderation.moderated_at.isoformat() if moderation.moderated_at else None,
                    "moderated_by_admin_id": (
                        str(moderation.moderated_by_admin_id)
                        if moderation.moderated_by_admin_id
                        else None
                    ),
                    "author": {
                        "id": str(author.id),
                        "telegram_id": author.telegram_id,
                        "username": author.username,
                        "display_name": " ".join(
                            part for part in (author.first_name, author.last_name or "") if part
                        ).strip()
                        or author.username
                        or "ROXY creator",
                    },
                }
            )
        return {"items": items, "total": total, "limit": limit, "offset": offset}


def install_feed_adult_moderation_contract() -> None:
    """Layer the adult-content state machine over the durable feed contract."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.admin_content import AdminContentService
    from app.services.feed import FeedError, FeedService

    previous_share_to_feed = FeedService.share_to_feed
    previous_to_card = FeedService.to_card
    previous_moderate_generation = AdminContentService.moderate_generation

    @classmethod
    async def share_to_feed_with_adult_queue(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        publication_scope: str,
        prompt_visible: bool = False,
        references_visible: bool = False,
        adult_content: bool = False,
    ) -> Generation:
        requested_scope = publication_scope
        generation = await previous_share_to_feed(
            session,
            generation_id=generation_id,
            owner_user_id=owner_user_id,
            publication_scope=publication_scope,
            prompt_visible=prompt_visible,
            references_visible=references_visible,
        )
        if requested_scope != "feed":
            return generation

        moderation = await session.get(GenerationModerationState, generation.id)
        if adult_content:
            generation.is_adult_content = True
            if moderation is None:
                moderation = GenerationModerationState(
                    generation_id=generation.id,
                    state="pending",
                    reason=None,
                    moderated_by_admin_id=None,
                    moderated_at=None,
                )
                session.add(moderation)
                await session.flush()

        # A moderation row is durable policy. Unchecking the client checkbox on a
        # later request must never bypass a pending/removed admin decision.
        if generation.is_adult_content and moderation is not None:
            generation.publication_scope = "feed"
            if moderation.state in _PUBLIC_STATES:
                generation.is_public_feed = True
                generation.is_profile_visible = True
                generation.feed_published_at = generation.feed_published_at or datetime.now(UTC)
            else:
                generation.is_public_feed = False
                generation.is_profile_visible = False
                if moderation.state == "pending":
                    generation.feed_published_at = None
            await session.flush()
        return generation

    @classmethod
    def surface_visible_with_moderation(
        cls,
        generation: Generation,
        *,
        surface: str,
        moderation_state: str | None = None,
    ) -> bool:
        if generation.status != "succeeded":
            return False
        if moderation_state is not None and moderation_state not in _PUBLIC_STATES:
            return False
        if surface == "feed":
            return bool(
                generation.publication_scope == "feed"
                and generation.is_public_feed
                and generation.is_profile_visible
            )
        return bool(
            generation.publication_scope in {"feed", "profile"}
            and generation.is_profile_visible
        )

    @classmethod
    async def get_feed_generations_with_adult(
        cls,
        session: AsyncSession,
        *,
        sort: str = "recent",
        limit: int = 20,
        offset: int = 0,
    ) -> list[Generation]:
        if sort not in {"recent", "top_day", "top"}:
            raise FeedError("Unknown feed sort")
        limit = max(1, min(limit, 50))
        offset = max(0, min(offset, 100_000))
        likes_count = (
            select(func.count())
            .select_from(GenerationLike)
            .where(GenerationLike.generation_id == Generation.id)
            .correlate(Generation)
            .scalar_subquery()
        )
        remix_count = (
            select(func.count())
            .select_from(FeedRemixEvent)
            .where(FeedRemixEvent.source_generation_id == Generation.id)
            .correlate(Generation)
            .scalar_subquery()
        )
        score = likes_count + Generation.shares_count * 5 + remix_count * 7
        moderation_visible = or_(
            GenerationModerationState.generation_id.is_(None),
            GenerationModerationState.state.in_(tuple(_PUBLIC_STATES)),
        )
        stmt = (
            select(Generation)
            .join(User, User.id == Generation.user_id)
            .outerjoin(
                GenerationModerationState,
                GenerationModerationState.generation_id == Generation.id,
            )
            .where(
                Generation.status == "succeeded",
                Generation.publication_scope == "feed",
                Generation.is_public_feed.is_(True),
                Generation.is_profile_visible.is_(True),
                User.is_active.is_(True),
                moderation_visible,
                cls._ready_media_condition(),
            )
        )
        if sort == "recent":
            stmt = stmt.order_by(
                Generation.feed_published_at.desc().nullslast(),
                Generation.id.desc(),
            )
        else:
            if sort == "top_day":
                stmt = stmt.where(
                    Generation.feed_published_at >= datetime.now(UTC) - timedelta(hours=24)
                )
            stmt = stmt.order_by(
                score.desc(),
                Generation.feed_published_at.desc().nullslast(),
                Generation.id.desc(),
            )
        return list((await session.scalars(stmt.offset(offset).limit(limit))).all())

    @classmethod
    async def get_user_feed_generations_with_adult(
        cls,
        session: AsyncSession,
        *,
        author_user_id: uuid.UUID,
        profile_visible_only: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Generation]:
        limit = max(1, min(limit, 50))
        offset = max(0, min(offset, 100_000))
        moderation_visible = or_(
            GenerationModerationState.generation_id.is_(None),
            GenerationModerationState.state.in_(tuple(_PUBLIC_STATES)),
        )
        stmt = (
            select(Generation)
            .join(User, User.id == Generation.user_id)
            .outerjoin(
                GenerationModerationState,
                GenerationModerationState.generation_id == Generation.id,
            )
            .where(
                Generation.user_id == author_user_id,
                Generation.status == "succeeded",
                User.is_active.is_(True),
                moderation_visible,
                cls._ready_media_condition(),
            )
        )
        if profile_visible_only:
            stmt = stmt.where(
                Generation.is_profile_visible.is_(True),
                Generation.publication_scope.in_(("feed", "profile")),
            )
        return list(
            (
                await session.scalars(
                    stmt.order_by(
                        Generation.feed_published_at.desc().nullslast(),
                        Generation.created_at.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )

    @classmethod
    async def to_card_with_adult_state(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        viewer_user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:
        card = await previous_to_card(
            session,
            generation,
            viewer_user_id=viewer_user_id,
            surface=surface,
        )
        moderation = await session.get(GenerationModerationState, generation.id)
        state = moderation.state if moderation else None
        card["adult_content"] = bool(generation.is_adult_content)
        card["moderation_state"] = state
        if state == "blurred":
            for key in ("result_url", "preview_url"):
                value = card.get(key)
                if isinstance(value, str):
                    card[key] = _blur_marker(value)
            result_urls = card.get("result_urls")
            if isinstance(result_urls, list):
                card["result_urls"] = [
                    _blur_marker(value) if isinstance(value, str) else value
                    for value in result_urls
                ]
            media = card.get("media")
            if isinstance(media, list):
                for item in media:
                    if not isinstance(item, dict):
                        continue
                    for key in ("url", "public_url", "download_url", "preview_url"):
                        value = item.get(key)
                        if isinstance(value, str):
                            item[key] = _blur_marker(value)
        return card

    async def moderate_generation_with_visibility(*args, **kwargs):  # type: ignore[no-untyped-def]
        result, replayed = await previous_moderate_generation(*args, **kwargs)
        session: AsyncSession = kwargs.get("session") if "session" in kwargs else args[0]
        generation_id = kwargs.get("generation_id")
        if generation_id is None:
            raise ValueError("generation_id is required")
        generation = await session.get(Generation, generation_id)
        moderation = await session.get(GenerationModerationState, generation_id)
        if generation is not None and moderation is not None:
            if moderation.state in _PUBLIC_STATES:
                generation.is_public_feed = generation.publication_scope == "feed"
                generation.is_profile_visible = generation.publication_scope in {"feed", "profile"}
                if generation.is_public_feed and generation.feed_published_at is None:
                    generation.feed_published_at = datetime.now(UTC)
            elif moderation.state == "removed":
                generation.is_public_feed = False
                generation.is_profile_visible = False
            await session.flush()
            result = {
                **result,
                "is_public_feed": bool(generation.is_public_feed),
                "is_profile_visible": bool(generation.is_profile_visible),
            }
        return result, replayed

    FeedService.share_to_feed = share_to_feed_with_adult_queue
    FeedService._surface_visible = surface_visible_with_moderation
    FeedService.get_feed_generations = get_feed_generations_with_adult
    FeedService.get_user_feed_generations = get_user_feed_generations_with_adult
    FeedService.to_card = to_card_with_adult_state
    AdminContentService.moderate_generation = staticmethod(moderate_generation_with_visibility)
