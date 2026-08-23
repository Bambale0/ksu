from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_content_models import GenerationModerationState
from app.db.feed_models import FeedComment, FeedRemixEvent
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.social_models import GenerationLike
from app.services.generations import GenerationService
from app.services.media_assets import MediaAssetService
from app.services.model_catalog import ModelCatalog, UnknownModelError
from app.services.reference_resolver import (
    PUBLIC_IMAGE_REFERENCE_FIELDS,
    PUBLIC_VIDEO_REFERENCE_FIELDS,
    ReferenceResolver,
)

FeedSurface = Literal["feed", "profile"]
FeedSort = Literal["recent", "top_day", "top"]
PublicationScope = Literal["private", "profile", "feed"]


class FeedError(ValueError):
    pass


class FeedNotFoundError(LookupError):
    pass


class FeedPublicationError(FeedError):
    pass


class FeedDerivativePublicationError(FeedPublicationError):
    pass


class FeedSurfaceError(FeedError):
    pass


class FeedMediaUnavailableError(FeedPublicationError):
    pass


class FeedService:
    COMMENT_MAX_LENGTH = 300
    # Runtime parity patches still read these class attrs. Keep them as aliases
    # to the shared resolver field set so feed cards and patches agree.
    REFERENCE_IMAGE_KEYS = PUBLIC_IMAGE_REFERENCE_FIELDS
    REFERENCE_VIDEO_KEYS = PUBLIC_VIDEO_REFERENCE_FIELDS

    @staticmethod
    def _validate_surface(surface: str) -> FeedSurface:
        if surface not in {"feed", "profile"}:
            raise FeedSurfaceError("Unknown feed surface")
        return surface  # type: ignore[return-value]

    @staticmethod
    def _moderation_visible(state: str | None) -> bool:
        return state != "removed"

    @classmethod
    def _surface_visible(
        cls,
        generation: Generation,
        *,
        surface: FeedSurface,
        moderation_state: str | None = None,
    ) -> bool:
        if generation.status != "succeeded" or not cls._moderation_visible(moderation_state):
            return False
        if surface == "feed":
            return bool(
                generation.publication_scope == "feed"
                and generation.is_public_feed
                and generation.is_profile_visible
                and not generation.is_adult_content
            )
        return bool(generation.publication_scope in {"feed", "profile"} and generation.is_profile_visible)

    @staticmethod
    def _ready_media_condition() -> Any:
        return exists(
            select(MediaAsset.id).where(
                MediaAsset.generation_id == Generation.id,
                MediaAsset.status == "ready",
                MediaAsset.object_key.is_not(None),
                MediaAsset.bucket.is_not(None),
            )
        )

    @staticmethod
    async def _has_ready_media(session: AsyncSession, generation_id: uuid.UUID) -> bool:
        return bool(
            await session.scalar(
                select(
                    exists().where(
                        MediaAsset.generation_id == generation_id,
                        MediaAsset.status == "ready",
                        MediaAsset.object_key.is_not(None),
                        MediaAsset.bucket.is_not(None),
                    )
                )
            )
        )

    @staticmethod
    async def _moderation_state(session: AsyncSession, generation_id: uuid.UUID) -> str | None:
        row = await session.get(GenerationModerationState, generation_id)
        return row.state if row is not None else None

    @classmethod
    async def assert_surface_visible(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        *,
        surface: str,
    ) -> Generation:
        normalized = cls._validate_surface(surface)
        generation = await session.get(Generation, generation_id)
        if generation is None:
            raise FeedNotFoundError("Publication not found")
        moderation_state = await cls._moderation_state(session, generation.id)
        if not cls._surface_visible(generation, surface=normalized, moderation_state=moderation_state):
            raise FeedNotFoundError("Publication not found")
        if not await cls._has_ready_media(session, generation.id):
            raise FeedNotFoundError("Publication media is unavailable")
        return generation

    @classmethod
    async def get_feed_generations(
        cls,
        session: AsyncSession,
        *,
        sort: FeedSort = "recent",
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
        stmt = (
            select(Generation)
            .join(User, User.id == Generation.user_id)
            .outerjoin(GenerationModerationState, GenerationModerationState.generation_id == Generation.id)
            .where(
                Generation.status == "succeeded",
                Generation.publication_scope == "feed",
                Generation.is_public_feed.is_(True),
                Generation.is_profile_visible.is_(True),
                Generation.is_adult_content.is_(False),
                User.is_active.is_(True),
                or_(
                    GenerationModerationState.generation_id.is_(None),
                    GenerationModerationState.state != "removed",
                ),
                cls._ready_media_condition(),
            )
        )
        if sort == "recent":
            stmt = stmt.order_by(Generation.feed_published_at.desc().nullslast(), Generation.id.desc())
        else:
            if sort == "top_day":
                stmt = stmt.where(
                    Generation.feed_published_at >= datetime.now(UTC) - timedelta(hours=24)
                )
            stmt = stmt.order_by(score.desc(), Generation.feed_published_at.desc().nullslast(), Generation.id.desc())
        return list((await session.scalars(stmt.offset(offset).limit(limit))).all())

    @classmethod
    async def get_user_feed_generations(
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
        stmt = (
            select(Generation)
            .join(User, User.id == Generation.user_id)
            .outerjoin(GenerationModerationState, GenerationModerationState.generation_id == Generation.id)
            .where(
                Generation.user_id == author_user_id,
                Generation.status == "succeeded",
                User.is_active.is_(True),
                or_(
                    GenerationModerationState.generation_id.is_(None),
                    GenerationModerationState.state != "removed",
                ),
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
    async def get_feed_generation_card(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        generation = await cls.assert_surface_visible(session, generation_id, surface="feed")
        return await cls.to_card(session, generation, viewer_user_id=viewer_user_id, surface="feed")

    @classmethod
    async def get_profile_generation_card(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        generation = await cls.assert_surface_visible(session, generation_id, surface="profile")
        return await cls.to_card(session, generation, viewer_user_id=viewer_user_id, surface="profile")

    @staticmethod
    def _provider_result_urls(generation: Generation) -> list[str]:
        raw = (generation.parameters or {}).get("_result_urls")
        values = [str(item) for item in raw] if isinstance(raw, list) else []
        if generation.result_url and generation.result_url not in values:
            values.insert(0, generation.result_url)
        return [item for item in values if item.startswith("https://")]

    @staticmethod
    def _asset_suffix(asset: MediaAsset) -> str:
        name = (asset.object_key or "").rsplit("/", 1)[-1]
        if "." not in name:
            return ""
        suffix = "." + name.rsplit(".", 1)[-1].lower()
        return suffix if 1 < len(suffix) <= 9 else ""

    @classmethod
    async def _media_views(cls, session: AsyncSession, generation: Generation) -> list[dict[str, Any]]:
        assets = list(
            (
                await session.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.generation_id == generation.id,
                        MediaAsset.status == "ready",
                        MediaAsset.object_key.is_not(None),
                        MediaAsset.bucket.is_not(None),
                    )
                    .order_by(MediaAsset.ordinal)
                )
            ).all()
        )
        if assets:
            views: list[dict[str, Any]] = []
            for asset in assets:
                view = dict(MediaAssetService.public_view(asset, server_route=True))
                route = f"/api/v1/media/{asset.id}/public/media{cls._asset_suffix(asset)}"
                view["url"] = route
                view["download_url"] = route
                view["public_url"] = route
                views.append(view)
            return views
        return [
            {
                "id": None,
                "url": url,
                "download_url": url,
                "content_type": None,
                "size_bytes": None,
                "ordinal": index,
            }
            for index, url in enumerate(cls._provider_result_urls(generation))
        ]

    @classmethod
    def _references(cls, generation: Generation) -> tuple[list[str], list[str]]:
        context = ReferenceResolver.generation_context(generation)
        return context.reference_images, context.reference_videos

    @classmethod
    async def to_card(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        viewer_user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:
        normalized_surface = cls._validate_surface(surface)
        moderation = await session.get(GenerationModerationState, generation.id)
        moderation_state = moderation.state if moderation else None
        if not cls._surface_visible(generation, surface=normalized_surface, moderation_state=moderation_state):
            raise FeedNotFoundError("Publication not found")
        author = await session.get(User, generation.user_id)
        if author is None or not author.is_active:
            raise FeedNotFoundError("Publication author not found")
        media = await cls._media_views(session, generation)
        if not media:
            raise FeedNotFoundError("Publication media is unavailable")
        like_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationLike)
                    .where(GenerationLike.generation_id == generation.id)
                )
            )
            or 0
        )
        liked_by_me = (await session.get(GenerationLike, (generation.id, viewer_user_id))) is not None
        comments_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(FeedComment)
                    .where(
                        FeedComment.generation_id == generation.id,
                        FeedComment.surface == normalized_surface,
                    )
                )
            )
            or 0
        )
        remixes = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(FeedRemixEvent)
                    .where(FeedRemixEvent.source_generation_id == generation.id)
                )
            )
            or 0
        )
        derivative = generation.source_feed_gen_id is not None
        prompt_hidden = derivative or not generation.feed_prompt_visible
        references_hidden = derivative or not generation.feed_references_visible
        reference_images, reference_videos = cls._references(generation)
        if references_hidden:
            reference_images = []
            reference_videos = []
        result_urls = [str(item["url"]) for item in media if item.get("url")]
        model_id = str((generation.parameters or {}).get("_model_id") or "") or None
        return {
            "id": str(generation.id),
            "task_id": str(generation.id),
            "user_id": str(generation.user_id),
            "model": model_id,
            "gen_type": generation.kind,
            "result_url": result_urls[0] if result_urls else None,
            "result_urls": result_urls,
            "preview_url": result_urls[0] if result_urls else None,
            "media": media,
            "prompt": "" if prompt_hidden else generation.prompt,
            "prompt_hidden": prompt_hidden,
            "prompt_actions_allowed": bool(not derivative and not prompt_hidden),
            "reference_images": reference_images,
            "reference_videos": reference_videos,
            "references_hidden": references_hidden,
            "likes_count": like_count,
            "liked_by_me": liked_by_me,
            "shares_count": int(generation.shares_count or 0),
            "comments_count": comments_count,
            "remixes": remixes,
            "author": {
                "id": str(author.id),
                "telegram_id": author.telegram_id,
                "username": author.username,
                "display_name": " ".join(
                    part for part in (author.first_name, author.last_name or "") if part
                ).strip()
                or author.username
                or "Пользователь Ксю",
            },
            "author_referral_code": str(author.telegram_id),
            "author_photo_url": None,
            "is_mine": generation.user_id == viewer_user_id,
            "feed_blurred": bool(moderation and moderation.state == "blurred"),
            "feed_prompt_visible": bool(generation.feed_prompt_visible and not derivative),
            "feed_references_visible": bool(generation.feed_references_visible and not derivative),
            "publication_scope": generation.publication_scope,
            "is_profile_visible": generation.is_profile_visible,
            "is_public_feed": generation.is_public_feed,
            "feed_interactions_enabled": (
                generation.publication_scope == "feed"
                if normalized_surface == "feed"
                else generation.is_profile_visible and generation.publication_scope in {"feed", "profile"}
            ),
            "surface": normalized_surface,
            "source_feed_gen_id": (
                str(generation.source_feed_gen_id) if generation.source_feed_gen_id else None
            ),
            "feed_published_at": (
                generation.feed_published_at.isoformat() if generation.feed_published_at else None
            ),
        }

    @classmethod
    async def cards_for_generations(
        cls,
        session: AsyncSession,
        generations: list[Generation],
        *,
        viewer_user_id: uuid.UUID,
        surface: str,
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for generation in generations:
            try:
                cards.append(
                    await cls.to_card(session, generation, viewer_user_id=viewer_user_id, surface=surface)
                )
            except FeedNotFoundError:
                continue
        return cards

    @classmethod
    async def share_to_feed(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        publication_scope: str,
        prompt_visible: bool = False,
        references_visible: bool = False,
    ) -> Generation:
        if publication_scope not in {"profile", "feed"}:
            raise FeedPublicationError("Publication scope must be profile or feed")
        generation = await session.scalar(
            select(Generation)
            .where(Generation.id == generation_id, Generation.user_id == owner_user_id)
            .with_for_update()
        )
        if generation is None:
            raise FeedNotFoundError("Generation not found")
        if generation.status != "succeeded":
            raise FeedPublicationError("Only completed generations can be published")
        if not generation.result_url and not cls._provider_result_urls(generation):
            raise FeedMediaUnavailableError("Generation media is not ready for publication")
        scope: PublicationScope = publication_scope  # type: ignore[assignment]
        if generation.source_feed_gen_id is not None and scope == "feed":
            raise FeedDerivativePublicationError("Derivative generations cannot be published to feed")
        if generation.is_adult_content and scope == "feed":
            scope = "profile"
        derivative = generation.source_feed_gen_id is not None
        generation.publication_scope = scope
        generation.is_public_feed = scope == "feed"
        generation.is_profile_visible = scope in {"feed", "profile"}
        generation.feed_prompt_visible = bool(prompt_visible and not derivative)
        generation.feed_references_visible = bool(references_visible and not derivative)
        generation.feed_published_at = datetime.now(UTC)
        await session.flush()
        return generation

    @classmethod
    async def remove_from_feed(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        target_scope: str = "private",
    ) -> Generation:
        if target_scope not in {"private", "profile"}:
            raise FeedPublicationError("Remove target must be private or profile")
        generation = await session.scalar(
            select(Generation)
            .where(Generation.id == generation_id, Generation.user_id == owner_user_id)
            .with_for_update()
        )
        if generation is None:
            raise FeedNotFoundError("Generation not found")
        generation.publication_scope = target_scope
        generation.is_public_feed = False
        generation.is_profile_visible = target_scope == "profile"
        if target_scope == "private":
            generation.feed_prompt_visible = False
            generation.feed_references_visible = False
        await session.flush()
        return generation

    @classmethod
    async def like_feed_generation(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:
        await cls.assert_surface_visible(session, generation_id, surface=surface)
        await session.execute(
            pg_insert(GenerationLike)
            .values(generation_id=generation_id, user_id=user_id)
            .on_conflict_do_nothing(index_elements=[GenerationLike.generation_id, GenerationLike.user_id])
        )
        await session.flush()
        count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationLike)
                    .where(GenerationLike.generation_id == generation_id)
                )
            )
            or 0
        )
        return {"liked_by_me": True, "likes_count": count}

    @classmethod
    async def unlike_feed_generation(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:
        await cls.assert_surface_visible(session, generation_id, surface=surface)
        await session.execute(
            delete(GenerationLike).where(
                GenerationLike.generation_id == generation_id,
                GenerationLike.user_id == user_id,
            )
        )
        await session.flush()
        count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationLike)
                    .where(GenerationLike.generation_id == generation_id)
                )
            )
            or 0
        )
        return {"liked_by_me": False, "likes_count": count}

    @classmethod
    async def increment_feed_share(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        surface: str,
    ) -> int:
        await cls.assert_surface_visible(session, generation_id, surface=surface)
        generation = await session.scalar(select(Generation).where(Generation.id == generation_id).with_for_update())
        if generation is None:
            raise FeedNotFoundError("Publication not found")
        generation.shares_count = int(generation.shares_count or 0) + 1
        await session.flush()
        return generation.shares_count

    @classmethod
    async def record_share(cls, session: AsyncSession, generation: Generation) -> None:
        generation.shares_count = int(generation.shares_count or 0) + 1
        await session.flush()

    @classmethod
    async def get_feed_comments(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        surface: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        normalized = cls._validate_surface(surface)
        await cls.assert_surface_visible(session, generation_id, surface=normalized)
        rows = list(
            (
                await session.execute(
                    select(FeedComment, User)
                    .join(User, User.id == FeedComment.user_id)
                    .where(
                        FeedComment.generation_id == generation_id,
                        FeedComment.surface == normalized,
                        User.is_active.is_(True),
                    )
                    .order_by(FeedComment.created_at.desc())
                    .offset(max(0, offset))
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        return [
            {
                "id": str(comment.id),
                "generation_id": str(comment.generation_id),
                "user_id": str(comment.user_id),
                "surface": comment.surface,
                "text": comment.text,
                "created_at": comment.created_at.isoformat(),
                "author": {
                    "id": str(author.id),
                    "username": author.username,
                    "display_name": author.first_name or author.username or "Пользователь Ксю",
                },
            }
            for comment, author in rows
        ]

    @classmethod
    async def comments(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        surface: str,
        viewer_user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        rows = await cls.get_feed_comments(session, generation_id=generation_id, surface=surface, limit=100)
        return [{**row, "is_mine": row["user_id"] == str(viewer_user_id)} for row in rows]

    @classmethod
    async def add_feed_comment(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
        surface: str,
        text: str,
    ) -> FeedComment:
        normalized = cls._validate_surface(surface)
        await cls.assert_surface_visible(session, generation_id, surface=normalized)
        clean = " ".join(text.strip().split())
        if not clean:
            raise FeedError("Comment cannot be empty")
        if len(clean) > cls.COMMENT_MAX_LENGTH:
            raise FeedError(f"Comment is limited to {cls.COMMENT_MAX_LENGTH} characters")
        item = FeedComment(
            generation_id=generation_id,
            user_id=user_id,
            surface=normalized,
            text=html.escape(clean, quote=False),
        )
        session.add(item)
        await session.flush()
        return item

    @classmethod
    async def add_comment(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
        surface: str,
        text: str,
    ) -> dict[str, Any]:
        row = await cls.add_feed_comment(
            session,
            generation_id=generation_id,
            user_id=user_id,
            surface=surface,
            text=text,
        )
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "text": row.text,
            "created_at": row.created_at.isoformat(),
            "is_mine": True,
            "author": "Вы",
        }

    @staticmethod
    def assert_prompt_library_publishable(generation: Generation) -> None:
        if generation.source_feed_gen_id is not None:
            raise FeedDerivativePublicationError("Derivative generations cannot be published to prompt library")

    @classmethod
    async def remix(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        source_generation_id: uuid.UUID,
        remix_author_id: uuid.UUID,
        surface: str,
    ) -> Generation:
        source = await cls.assert_surface_visible(session, source_generation_id, surface=surface)
        model_id = str((source.parameters or {}).get("_model_id") or "")
        if not model_id:
            raise FeedError("Source model is not reusable")
        try:
            spec = ModelCatalog.get(model_id)
        except UnknownModelError as exc:
            raise FeedError("Source model is no longer available") from exc
        allowed = set(spec.known_fields)
        source_parameters = {
            key: value
            for key, value in dict(source.parameters or {}).items()
            if not key.startswith("_") and key in allowed and key != "prompt"
        }
        generation = await GenerationService.create(
            session,
            redis,
            user_id=remix_author_id,
            model_id=model_id,
            prompt=source.prompt,
            input_url=source.input_url,
            parameters=source_parameters,
            billing_seconds=(source.parameters or {}).get("_billing_seconds"),
            source_feed_gen_id=source.id,
            parent_generation_id=source.id,
            action_type="remix",
        )
        session.add(
            FeedRemixEvent(
                source_generation_id=source.id,
                remix_generation_id=generation.id,
                source_author_id=source.user_id,
                remix_author_id=remix_author_id,
                credits_spent=Decimal(generation.cost_rox),
            )
        )
        await session.commit()
        return generation

    @classmethod
    async def create_remix(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        source_generation_id: uuid.UUID,
        user_id: uuid.UUID,
        prompt: str | None = None,
    ) -> Generation:
        source = await cls.assert_surface_visible(session, source_generation_id, surface="feed")
        if prompt and prompt.strip():
            source.prompt = prompt.strip()
        return await cls.remix(
            session,
            redis,
            source_generation_id=source_generation_id,
            remix_author_id=user_id,
            surface="feed",
        )

    @staticmethod
    def _bot_username() -> str:
        return settings.bot_username.strip().lstrip("@")

    @classmethod
    def post_deep_link(cls, generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        username = cls._bot_username()
        if not username:
            return None
        return f"https://t.me/{username}?start=feed_{generation_id}_ref_{author_referral_code}"

    @classmethod
    def profile_deep_link(cls, author_referral_code: str) -> str | None:
        username = cls._bot_username()
        if not username:
            return None
        return f"https://t.me/{username}?start=posts_{author_referral_code}_ref_{author_referral_code}"

    @classmethod
    def remix_deep_link(cls, generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        username = cls._bot_username()
        if not username:
            return None
        return f"https://t.me/{username}?start=remix_{generation_id}_ref_{author_referral_code}"

    @staticmethod
    async def author_by_referral_code(session: AsyncSession, referral_code: str) -> User:
        try:
            telegram_id = int(referral_code)
        except ValueError as exc:
            raise FeedNotFoundError("Profile not found") from exc
        author = await session.scalar(
            select(User).where(User.telegram_id == telegram_id, User.is_active.is_(True))
        )
        if author is None:
            raise FeedNotFoundError("Profile not found")
        return author
