from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation, User
from app.db.profile_models import UserPreference
from app.db.social_models import GenerationLike, UserSubscription


class SocialProfileNotFoundError(LookupError):
    pass


class SelfSubscriptionError(ValueError):
    pass


class SocialService:
    @staticmethod
    async def owned_generation(
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Generation | None:
        return await session.scalar(
            select(Generation).where(
                Generation.id == generation_id,
                Generation.user_id == user_id,
            )
        )

    @staticmethod
    async def generation_like_state(
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
    ) -> dict[str, object]:
        like_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationLike)
                    .where(GenerationLike.generation_id == generation_id)
                )
            )
            or 0
        )
        liked_by_me = (
            await session.get(GenerationLike, (generation_id, viewer_user_id))
        ) is not None
        return {"liked_by_me": liked_by_me, "like_count": like_count}

    @classmethod
    async def like_generation(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, object]:
        await session.execute(
            insert(GenerationLike)
            .values(generation_id=generation_id, user_id=user_id)
            .on_conflict_do_nothing(
                index_elements=[GenerationLike.generation_id, GenerationLike.user_id]
            )
        )
        await session.flush()
        return await cls.generation_like_state(
            session,
            generation_id=generation_id,
            viewer_user_id=user_id,
        )

    @classmethod
    async def unlike_generation(
        cls,
        session: AsyncSession,
        *,
        generation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, object]:
        await session.execute(
            delete(GenerationLike).where(
                GenerationLike.generation_id == generation_id,
                GenerationLike.user_id == user_id,
            )
        )
        await session.flush()
        return await cls.generation_like_state(
            session,
            generation_id=generation_id,
            viewer_user_id=user_id,
        )

    @staticmethod
    def _display_name(user: User) -> str:
        parts = [user.first_name.strip()]
        if user.last_name:
            parts.append(user.last_name.strip())
        value = " ".join(part for part in parts if part).strip()
        return value or user.username or "Пользователь Ксю"

    @classmethod
    async def public_profile(
        cls,
        session: AsyncSession,
        *,
        author_user_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
    ) -> dict[str, object]:
        author = await session.get(User, author_user_id)
        if author is None or not author.is_active:
            raise SocialProfileNotFoundError
        preference = await session.get(UserPreference, author_user_id)
        discoverable = bool(preference and preference.profile_discoverable)
        is_self = author_user_id == viewer_user_id
        if not is_self and not discoverable:
            raise SocialProfileNotFoundError

        follower_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(UserSubscription)
                    .where(UserSubscription.author_user_id == author_user_id)
                )
            )
            or 0
        )
        subscribed_by_me = False
        if not is_self:
            subscribed_by_me = (
                await session.get(
                    UserSubscription,
                    (viewer_user_id, author_user_id),
                )
            ) is not None

        return {
            "id": str(author.id),
            "display_name": cls._display_name(author),
            "username": author.username,
            "profile_discoverable": discoverable,
            "is_self": is_self,
            "subscribed_by_me": subscribed_by_me,
            "follower_count": follower_count,
        }

    @classmethod
    async def subscribe(
        cls,
        session: AsyncSession,
        *,
        author_user_id: uuid.UUID,
        subscriber_user_id: uuid.UUID,
    ) -> dict[str, object]:
        if author_user_id == subscriber_user_id:
            raise SelfSubscriptionError("Cannot subscribe to yourself")
        await cls.public_profile(
            session,
            author_user_id=author_user_id,
            viewer_user_id=subscriber_user_id,
        )
        await session.execute(
            insert(UserSubscription)
            .values(
                subscriber_user_id=subscriber_user_id,
                author_user_id=author_user_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    UserSubscription.subscriber_user_id,
                    UserSubscription.author_user_id,
                ]
            )
        )
        await session.flush()
        return await cls.public_profile(
            session,
            author_user_id=author_user_id,
            viewer_user_id=subscriber_user_id,
        )

    @classmethod
    async def unsubscribe(
        cls,
        session: AsyncSession,
        *,
        author_user_id: uuid.UUID,
        subscriber_user_id: uuid.UUID,
    ) -> dict[str, object]:
        if author_user_id == subscriber_user_id:
            raise SelfSubscriptionError("Cannot unsubscribe from yourself")
        await session.execute(
            delete(UserSubscription).where(
                UserSubscription.subscriber_user_id == subscriber_user_id,
                UserSubscription.author_user_id == author_user_id,
            )
        )
        await session.flush()

        author = await session.get(User, author_user_id)
        preference = await session.get(UserPreference, author_user_id) if author else None
        discoverable = bool(author and author.is_active and preference and preference.profile_discoverable)
        if discoverable:
            return await cls.public_profile(
                session,
                author_user_id=author_user_id,
                viewer_user_id=subscriber_user_id,
            )
        return {
            "id": str(author_user_id),
            "display_name": "Скрытый профиль",
            "username": None,
            "profile_discoverable": False,
            "is_self": False,
            "subscribed_by_me": False,
            "follower_count": 0,
        }

    @classmethod
    async def subscriptions(
        cls,
        session: AsyncSession,
        *,
        subscriber_user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        rows = list(
            (
                await session.execute(
                    select(UserSubscription, User, UserPreference)
                    .join(User, User.id == UserSubscription.author_user_id)
                    .outerjoin(UserPreference, UserPreference.user_id == User.id)
                    .where(UserSubscription.subscriber_user_id == subscriber_user_id)
                    .order_by(UserSubscription.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        result: list[dict[str, object]] = []
        for subscription, author, preference in rows:
            discoverable = bool(
                author.is_active and preference and preference.profile_discoverable
            )
            result.append(
                {
                    "id": str(author.id),
                    "display_name": (
                        cls._display_name(author) if discoverable else "Скрытый профиль"
                    ),
                    "username": author.username if discoverable else None,
                    "profile_discoverable": discoverable,
                    "subscribed_by_me": True,
                    "subscribed_at": subscription.created_at.isoformat(),
                }
            )
        return result
