from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.feed_models import FeedComment
from app.db.history_models import GenerationHistoryState
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.db.social_models import GenerationLike
from app.services.feed import (
    FeedDerivativePublicationError,
    FeedMediaUnavailableError,
    FeedNotFoundError,
    FeedService,
)
from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError


def _telegram_id() -> int:
    return random.randint(8_000_000_000_000, 8_999_999_999_999)


async def _user(session, name: str = "Feed") -> User:  # type: ignore[no-untyped-def]
    user = User(telegram_id=_telegram_id(), first_name=name)
    session.add(user)
    await session.flush()
    return user


async def _pending_generation(
    session,
    user: User,
    *,
    kind: str = "text_to_image",
    suffix: str = ".png",
    source_feed_gen_id=None,
    adult: bool = False,
    prompt: str = "secret source prompt",
) -> Generation:  # type: ignore[no-untyped-def]
    generation = Generation(
        user_id=user.id,
        kind=kind,
        status="succeeded",
        prompt=prompt,
        result_url=f"https://example.invalid/{random.randint(1, 999999999)}{suffix}",
        input_url="https://example.invalid/private-reference.png",
        cost_rox=Decimal("1.00"),
        provider="kie",
        parameters={
            "_model_id": "nano-banana-2",
            "image_url": "https://example.invalid/private-reference.png",
        },
        source_feed_gen_id=source_feed_gen_id,
        parent_generation_id=source_feed_gen_id,
        action_type="remix" if source_feed_gen_id else None,
        is_adult_content=adult,
    )
    session.add(generation)
    await session.commit()
    return generation


def _fixture_media_bytes(suffix: str) -> bytes:
    if suffix.lower() in {".mp4", ".mov"}:
        return b"\x00\x00\x00\x18ftypisom0000roxy-feed-fixture"
    if suffix.lower() == ".webm":
        return b"\x1aE\xdf\xa3roxy-feed-fixture"
    if suffix.lower() in {".jpg", ".jpeg"}:
        return b"\xff\xd8\xffroxy-feed-fixture"
    if suffix.lower() == ".webp":
        return b"RIFF\x10\x00\x00\x00WEBProxy-feed-fixture"
    return b"\x89PNG\r\n\x1a\nroxy-feed-fixture"


async def _ready_generation(
    session,
    user: User,
    *,
    kind: str = "text_to_image",
    suffix: str = ".png",
    content_type: str = "image/png",
    source_feed_gen_id=None,
    adult: bool = False,
    prompt: str = "secret source prompt",
) -> Generation:  # type: ignore[no-untyped-def]
    generation = await _pending_generation(
        session,
        user,
        kind=kind,
        suffix=suffix,
        source_feed_gen_id=source_feed_gen_id,
        adult=adult,
        prompt=prompt,
    )
    provider_url = generation.result_url
    extension = ".mp4" if suffix.lower() in {".mp4", ".mov"} else suffix.lower()
    filename = f"test-{generation.id}{extension}"
    path = FeedStaticStorage.ensure_root() / filename
    path.write_bytes(_fixture_media_bytes(extension))
    local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"
    params = dict(generation.parameters or {})
    params["_provider_result_urls"] = [provider_url]
    params["_result_urls"] = [local_url]
    params["_feed_static"] = True
    generation.parameters = params
    generation.result_url = local_url
    session.add(
        MediaAsset(
            generation_id=generation.id,
            user_id=user.id,
            ordinal=0,
            source_url=provider_url,
            status="ready",
            bucket="test-feed",
            object_key=f"feed/{generation.id}{suffix}",
            content_type=content_type,
            size_bytes=1024,
        )
    )
    await session.commit()
    return generation


@pytest.mark.asyncio
async def test_completed_image_generation_publishes_to_feed() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Image")
        generation = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
            prompt_visible=True,
            references_visible=True,
        )
        await session.commit()

        rows = await FeedService.get_feed_generations(session, sort="recent")
        assert generation.id in {row.id for row in rows}
        card = await FeedService.get_feed_generation_card(
            session,
            generation_id=generation.id,
            viewer_user_id=author.id,
        )
        assert card["publication_scope"] == "feed"
        assert card["is_public_feed"] is True
        assert card["is_profile_visible"] is True
        assert card["prompt"] == "secret source prompt"
        assert str(card["result_url"]).startswith(FeedStaticStorage.public_prefix() + "/")
        assert card["media"][0]["storage"] == "static"


@pytest.mark.asyncio
async def test_publish_fails_closed_when_static_persistence_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async with SessionFactory() as session:
        author = await _user(session, "Pending")
        generation = await _pending_generation(session, author)

        async def fail_persist(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise FeedStaticStorageError("provider unavailable")

        monkeypatch.setattr(FeedStaticStorage, "persist_urls", fail_persist)
        with pytest.raises(FeedMediaUnavailableError):
            await FeedService.share_to_feed(
                session,
                generation_id=generation.id,
                owner_user_id=author.id,
                publication_scope="feed",
            )

        await session.refresh(generation)
        assert generation.publication_scope == "private"
        assert generation.is_public_feed is False
        assert generation.is_profile_visible is False
        assert generation.feed_published_at is None


@pytest.mark.asyncio
async def test_completed_video_generation_publishes_with_video_result() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Video")
        generation = await _ready_generation(
            session,
            author,
            kind="text_to_video",
            suffix=".mp4",
            content_type="video/mp4",
        )
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
        )
        await session.commit()
        card = await FeedService.get_feed_generation_card(
            session,
            generation_id=generation.id,
            viewer_user_id=author.id,
        )
        assert card["gen_type"] == "text_to_video"
        assert str(card["result_url"]).endswith(".mp4")
        assert card["media"][0]["content_type"] == "video/mp4"
        assert card["media"][0]["storage"] == "static"


@pytest.mark.asyncio
async def test_profile_only_is_excluded_from_discovery_but_in_author_profile() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Profile")
        generation = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="profile",
        )
        await session.commit()

        public_rows = await FeedService.get_feed_generations(session, sort="recent")
        assert generation.id not in {row.id for row in public_rows}
        profile_rows = await FeedService.get_user_feed_generations(
            session,
            author_user_id=author.id,
            profile_visible_only=True,
        )
        assert generation.id in {row.id for row in profile_rows}
        with pytest.raises(FeedNotFoundError):
            await FeedService.get_feed_generation_card(
                session,
                generation_id=generation.id,
                viewer_user_id=author.id,
            )
        card = await FeedService.get_profile_generation_card(
            session,
            generation_id=generation.id,
            viewer_user_id=author.id,
        )
        assert card["publication_scope"] == "profile"
        assert card["surface"] == "profile"


@pytest.mark.asyncio
async def test_adult_feed_request_is_downgraded_to_profile() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Adult")
        generation = await _ready_generation(session, author, adult=True)
        published = await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
        )
        await session.commit()
        assert published.publication_scope == "profile"
        assert published.is_public_feed is False
        assert published.is_profile_visible is True
        rows = await FeedService.get_feed_generations(session)
        assert generation.id not in {row.id for row in rows}


@pytest.mark.asyncio
async def test_derivative_cannot_publish_feed_or_prompt_library_and_hides_source_data() -> None:
    async with SessionFactory() as session:
        source_author = await _user(session, "Source")
        remix_author = await _user(session, "Remixer")
        source = await _ready_generation(session, source_author, prompt="private source prompt")
        await FeedService.share_to_feed(
            session,
            generation_id=source.id,
            owner_user_id=source_author.id,
            publication_scope="feed",
            prompt_visible=True,
            references_visible=True,
        )
        await session.commit()

        derivative = await _ready_generation(
            session,
            remix_author,
            source_feed_gen_id=source.id,
            prompt="private source prompt",
        )
        with pytest.raises(FeedDerivativePublicationError):
            await FeedService.share_to_feed(
                session,
                generation_id=derivative.id,
                owner_user_id=remix_author.id,
                publication_scope="feed",
                prompt_visible=True,
                references_visible=True,
            )
        with pytest.raises(FeedDerivativePublicationError):
            FeedService.assert_prompt_library_publishable(derivative)

        await FeedService.share_to_feed(
            session,
            generation_id=derivative.id,
            owner_user_id=remix_author.id,
            publication_scope="profile",
            prompt_visible=True,
            references_visible=True,
        )
        await session.commit()
        card = await FeedService.get_profile_generation_card(
            session,
            generation_id=derivative.id,
            viewer_user_id=source_author.id,
        )
        assert card["prompt"] == ""
        assert card["prompt_hidden"] is True
        assert card["prompt_actions_allowed"] is False
        assert card["reference_images"] == []
        assert card["reference_videos"] == []
        assert card["references_hidden"] is True
        assert "private source prompt" not in repr(card)
        assert "private-reference" not in repr(card)


@pytest.mark.asyncio
async def test_like_is_idempotent_and_share_increments() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Author")
        viewer = await _user(session, "Viewer")
        generation = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
        )
        await session.commit()

        first = await FeedService.like_feed_generation(
            session,
            generation_id=generation.id,
            user_id=viewer.id,
            surface="feed",
        )
        second = await FeedService.like_feed_generation(
            session,
            generation_id=generation.id,
            user_id=viewer.id,
            surface="feed",
        )
        await session.commit()
        assert first["likes_count"] == 1
        assert second["likes_count"] == 1
        count = await session.scalar(
            select(func.count())
            .select_from(GenerationLike)
            .where(GenerationLike.generation_id == generation.id)
        )
        assert int(count or 0) == 1

        assert await FeedService.increment_feed_share(
            session,
            generation_id=generation.id,
            surface="feed",
        ) == 1
        assert await FeedService.increment_feed_share(
            session,
            generation_id=generation.id,
            surface="feed",
        ) == 2
        await session.commit()


@pytest.mark.asyncio
async def test_comments_are_surface_scoped_and_profile_only_rejects_feed_comment() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "Comments")
        viewer = await _user(session, "Viewer")
        generation = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
        )
        await session.commit()

        await FeedService.add_feed_comment(
            session,
            generation_id=generation.id,
            user_id=viewer.id,
            surface="feed",
            text="  hello   <b>feed</b>  ",
        )
        await FeedService.add_feed_comment(
            session,
            generation_id=generation.id,
            user_id=viewer.id,
            surface="profile",
            text="profile comment",
        )
        await session.commit()
        feed_comments = await FeedService.get_feed_comments(
            session,
            generation_id=generation.id,
            surface="feed",
        )
        profile_comments = await FeedService.get_feed_comments(
            session,
            generation_id=generation.id,
            surface="profile",
        )
        assert len(feed_comments) == 1
        assert len(profile_comments) == 1
        assert feed_comments[0]["text"] == "hello &lt;b&gt;feed&lt;/b&gt;"
        assert profile_comments[0]["text"] == "profile comment"

        profile_only = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=profile_only.id,
            owner_user_id=author.id,
            publication_scope="profile",
        )
        await session.commit()
        with pytest.raises(FeedNotFoundError):
            await FeedService.add_feed_comment(
                session,
                generation_id=profile_only.id,
                user_id=viewer.id,
                surface="feed",
                text="not allowed",
            )
        await FeedService.add_feed_comment(
            session,
            generation_id=profile_only.id,
            user_id=viewer.id,
            surface="profile",
            text="allowed",
        )
        await session.commit()
        count = await session.scalar(
            select(func.count())
            .select_from(FeedComment)
            .where(FeedComment.generation_id == profile_only.id)
        )
        assert int(count or 0) == 1


@pytest.mark.asyncio
async def test_history_hiding_does_not_unpublish_feed_item() -> None:
    async with SessionFactory() as session:
        author = await _user(session, "History")
        generation = await _ready_generation(session, author)
        await FeedService.share_to_feed(
            session,
            generation_id=generation.id,
            owner_user_id=author.id,
            publication_scope="feed",
        )
        session.add(
            GenerationHistoryState(
                generation_id=generation.id,
                user_id=author.id,
                hidden_at=datetime.now(UTC),
            )
        )
        await session.commit()
        card = await FeedService.get_feed_generation_card(
            session,
            generation_id=generation.id,
            viewer_user_id=author.id,
        )
        assert card["id"] == str(generation.id)
