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
        return value or user.username or "Пользователь ROXY"

    @staticmethod
    async def _has_public_profile_work(session: AsyncSession, author_user_id: uuid.UUID) -> bool:
        return bool(
            await session.scalar(
                select(Generation.id)
                .where(
                    Generation.user_id == author_user_id,
                    Generation.status == "succeeded",
                    Generation.is_profile_visible.is_(True),
                    Generation.publication_scope.in_(("feed", "profile")),
                )
                .limit(1)
            )
        )

    @classmethod
    async def _profile_publicly_available(
        cls,
        session: AsyncSession,
        *,
        author: User,
        preference: UserPreference | None,
    ) -> bool:
        if not author.is_active:
            return False
        if preference and preference.profile_discoverable:
            return True
        return await cls._has_public_profile_work(session, author.id)

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
        is_self = author_user_id == viewer_user_id
        profile_available = await cls._profile_publicly_available(
            session,
            author=author,
            preference=preference,
        )
        if not is_self and not profile_available:
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
            "referral_code": str(author.telegram_id),
            "profile_discoverable": profile_available,
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
        profile_available = bool(
            author
            and await cls._profile_publicly_available(
                session,
                author=author,
                preference=preference,
            )
        )
        if profile_available and author is not None:
            return await cls.public_profile(
                session,
                author_user_id=author_user_id,
                viewer_user_id=subscriber_user_id,
            )
        return {
            "id": str(author_user_id),
            "display_name": "Скрытый профиль",
            "username": None,
            "referral_code": None,
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
            profile_available = await cls._profile_publicly_available(
                session,
                author=author,
                preference=preference,
            )
            result.append(
                {
                    "id": str(author.id),
                    "display_name": (
                        cls._display_name(author) if profile_available else "Скрытый профиль"
                    ),
                    "username": author.username if profile_available else None,
                    "referral_code": str(author.telegram_id) if profile_available else None,
                    "profile_discoverable": profile_available,
                    "subscribed_by_me": True,
                    "subscribed_at": subscription.created_at.isoformat(),
                }
            )
        return result
