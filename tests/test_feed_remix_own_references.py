from __future__ import annotations

import random
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.feed_models import FeedRemixEvent
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.feed_remix import FeedRemixReferenceError, FeedRemixService
from app.services.feed_seedance_replay import PRIVATE_AUTHOR_REPLAY_MARKER
from app.services.feed_static import FeedStaticStorage
from app.services.references import ReferenceService


def _telegram_id() -> int:
    return random.randint(9_900_000_000_000, 9_999_999_999_999)


async def _noop_wake(_cls, _redis, _generation_ids) -> None:  # type: ignore[no-untyped-def]
    return None


async def _public_source(session, *, author: User) -> Generation:  # type: ignore[no-untyped-def]
    provider_url = "https://example.invalid/source-remix-own-ref.png"
    source_reference = "https://example.invalid/author-reference.png"
    source = Generation(
        user_id=author.id,
        kind="image_to_image",
        status="succeeded",
        prompt="hidden author prompt",
        input_url=source_reference,
        result_url=provider_url,
        cost_rox=Decimal("8.00"),
        provider="kie",
        parameters={
            "_model_id": "nano-banana-2",
            "_requested_model_id": "nano-banana-2",
            "_billing_seconds": None,
            "image_url": source_reference,
        },
        publication_scope="feed",
        is_public_feed=True,
        is_profile_visible=True,
        feed_prompt_visible=False,
        feed_references_visible=False,
    )
    session.add(source)
    await session.flush()

    filename = f"test-remix-own-ref-{source.id}.png"
    (FeedStaticStorage.ensure_root() / filename).write_bytes(
        b"\x89PNG\r\n\x1a\nroxy-feed-remix-own-reference"
    )
    local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"
    source.result_url = local_url
    source.parameters = {
        **source.parameters,
        "_provider_result_urls": [provider_url],
        "_result_urls": [local_url],
        "_feed_static": True,
    }
    session.add(
        MediaAsset(
            generation_id=source.id,
            user_id=author.id,
            ordinal=0,
            source_url=provider_url,
            status="ready",
            bucket="test-feed",
            object_key=f"feed/{source.id}.png",
            content_type="image/png",
        )
    )
    await session.commit()
    return source


async def _public_seedance_source(
    session,
    *,
    author: User,
    author_video: str | None,
) -> tuple[Generation, Path]:  # type: ignore[no-untyped-def]
    provider_url = "https://example.invalid/author-rendered-result.mp4"
    author_photo = "https://example.invalid/author-identity.jpg"
    parameters: dict[str, object] = {
        "_model_id": "seedance-2.5",
        "_requested_model_id": "seedance-2.5",
        "_billing_seconds": 10,
        "reference_image_urls": [author_photo],
        "duration": 10,
        "resolution": "720p",
        "aspect_ratio": "9:16",
    }
    if author_video:
        parameters["reference_video_urls"] = [author_video]
    source = Generation(
        user_id=author.id,
        kind="reference_to_video",
        status="succeeded",
        prompt="author seedance prompt",
        result_url=provider_url,
        cost_rox=Decimal("70.00"),
        provider="neironych",
        parameters=parameters,
        publication_scope="feed",
        is_public_feed=True,
        is_profile_visible=True,
        feed_prompt_visible=False,
        feed_references_visible=False,
    )
    session.add(source)
    await session.flush()

    filename = f"test-seedance-author-recipe-{source.id}.mp4"
    target = FeedStaticStorage.ensure_root() / filename
    target.write_bytes(b"synthetic-seedance-feed-video")
    local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"
    source.result_url = local_url
    source.parameters = {
        **parameters,
        "_provider_result_urls": [provider_url],
        "_result_urls": [local_url],
        "_feed_static": True,
    }
    session.add(
        MediaAsset(
            generation_id=source.id,
            user_id=author.id,
            ordinal=0,
            source_url=provider_url,
            status="ready",
            bucket="test-feed",
            object_key=f"feed/{source.id}.mp4",
            content_type="video/mp4",
        )
    )
    await session.commit()
    return source, target


@pytest.mark.asyncio
async def test_prepare_feed_remix_hides_prompt_and_never_inherits_author_reference() -> None:
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([author, remixer])
        await session.flush()
        source = await _public_source(session, author=author)

        prepared = await FeedRemixService.prepare(
            session,
            source_generation_id=source.id,
            viewer_user_id=remixer.id,
            surface="feed",
        )

        assert prepared["prompt"] == ""
        assert prepared["prompt_hidden"] is True
        assert prepared["prompt_editable"] is False
        assert prepared["reference_requirements"] == {
            "image_count": 1,
            "video_count": 0,
            "audio_count": 0,
            "required": True,
        }
        assert "image_url" not in prepared["settings"]
        assert "https://example.invalid/author-reference.png" not in str(prepared)

        filename = FeedStaticStorage.path_for_url(str(source.result_url))
        if filename is not None:
            filename.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_feed_remix_requires_owned_references_and_launches_with_only_remixer_media(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        stranger = User(telegram_id=_telegram_id(), first_name="Stranger")
        session.add_all([author, remixer, stranger])
        await session.flush()
        source = await _public_source(session, author=author)

        own_reference, _ = await ReferenceService.register(
            session,
            user_id=remixer.id,
            source_url="https://example.invalid/remixer-reference.png",
            kind="image",
            source="test",
        )
        foreign_reference, _ = await ReferenceService.register(
            session,
            user_id=stranger.id,
            source_url="https://example.invalid/stranger-reference.png",
            kind="image",
            source="test",
        )

        with pytest.raises(FeedRemixReferenceError):
            await FeedRemixService.quote(
                session,
                source_generation_id=source.id,
                remix_author_id=remixer.id,
                surface="feed",
                prompt_override=None,
                reference_ids=[],
                confirm_own_references=True,
            )

        with pytest.raises(FeedRemixReferenceError):
            await FeedRemixService.quote(
                session,
                source_generation_id=source.id,
                remix_author_id=remixer.id,
                surface="feed",
                prompt_override=None,
                reference_ids=[foreign_reference.id],
                confirm_own_references=True,
            )

        captured: dict[str, object] = {}

        async def fake_create(
            _cls,
            target_session,
            _redis,
            *,
            user_id,
            model_id,
            prompt,
            input_url,
            parameters,
            billing_seconds,
            source_feed_gen_id,
            parent_generation_id,
            action_type,
            commit,
            wake,
        ):
            captured.update(
                {
                    "user_id": user_id,
                    "model_id": model_id,
                    "prompt": prompt,
                    "input_url": input_url,
                    "parameters": dict(parameters),
                    "billing_seconds": billing_seconds,
                    "source_feed_gen_id": source_feed_gen_id,
                    "parent_generation_id": parent_generation_id,
                    "action_type": action_type,
                    "commit": commit,
                    "wake": wake,
                }
            )
            generation = Generation(
                user_id=user_id,
                kind="image_to_image",
                status="queued",
                prompt=prompt,
                input_url=input_url,
                cost_rox=Decimal("8.00"),
                provider="kie",
                parameters={"_model_id": model_id, **parameters},
                source_feed_gen_id=source_feed_gen_id,
                parent_generation_id=parent_generation_id,
                action_type=action_type,
                publication_scope="private",
                is_public_feed=False,
                is_profile_visible=False,
                feed_prompt_visible=False,
                feed_references_visible=False,
            )
            target_session.add(generation)
            await target_session.flush()
            return generation

        monkeypatch.setattr("app.services.feed_remix.GenerationService.create", classmethod(fake_create))
        monkeypatch.setattr("app.services.feed_remix.GenerationService.wake", classmethod(_noop_wake))
        generation = await FeedRemixService.launch(
            session,
            object(),  # type: ignore[arg-type]
            source_generation_id=source.id,
            remix_author_id=remixer.id,
            surface="feed",
            prompt_override="must not replace hidden prompt",
            reference_ids=[own_reference.id],
            confirm_own_references=True,
        )

        assert captured["prompt"] == "hidden author prompt"
        assert captured["input_url"] is None
        assert captured["parameters"] == {
            "reference_images": ["https://example.invalid/remixer-reference.png"]
        }
        assert "author-reference.png" not in str(captured)
        assert captured["source_feed_gen_id"] == source.id
        assert captured["parent_generation_id"] == source.id
        assert captured["action_type"] == "remix"
        assert captured["commit"] is False
        assert captured["wake"] is False
        assert generation.source_feed_gen_id == source.id
        assert not (generation.parameters or {}).get(PRIVATE_AUTHOR_REPLAY_MARKER)

        event = await session.scalar(
            select(FeedRemixEvent).where(FeedRemixEvent.remix_generation_id == generation.id)
        )
        assert event is not None
        assert event.source_generation_id == source.id
        assert event.source_author_id == author.id
        assert event.remix_author_id == remixer.id

        filename = FeedStaticStorage.path_for_url(str(source.result_url))
        if filename is not None:
            filename.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_seedance_prepare_restores_author_video_privately_and_requests_identity_photo() -> None:
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([author, remixer])
        await session.flush()
        author_video = "https://example.invalid/author-motion.mp4"
        source, target = await _public_seedance_source(
            session,
            author=author,
            author_video=author_video,
        )

        try:
            prepared = await FeedRemixService.prepare(
                session,
                source_generation_id=source.id,
                viewer_user_id=remixer.id,
                surface="feed",
            )

            assert prepared["source_has_video_reference"] is True
            assert prepared["reference_requirements"] == {
                "image_count": 1,
                "video_count": 0,
                "audio_count": 0,
                "required": True,
            }
            assert author_video not in str(prepared)
            assert "author-identity.jpg" not in str(prepared)
        finally:
            target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_seedance_launch_uses_viewer_identity_photo_and_author_motion_video(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([author, remixer])
        await session.flush()
        author_video = "https://example.invalid/author-motion.mp4"
        source, target = await _public_seedance_source(
            session,
            author=author,
            author_video=author_video,
        )
        viewer_photo, _ = await ReferenceService.register(
            session,
            user_id=remixer.id,
            source_url="https://example.invalid/viewer-identity.jpg",
            kind="image",
            source="test",
        )
        captured: dict[str, object] = {}

        async def fake_create(
            _cls,
            target_session,
            _redis,
            **kwargs,
        ):
            captured.update(kwargs)
            generation = Generation(
                user_id=kwargs["user_id"],
                kind="reference_to_video",
                status="queued",
                prompt=kwargs["prompt"],
                input_url=kwargs["input_url"],
                cost_rox=Decimal("70.00"),
                provider="neironych",
                parameters={"_model_id": kwargs["model_id"], **kwargs["parameters"]},
                source_feed_gen_id=kwargs["source_feed_gen_id"],
                parent_generation_id=kwargs["parent_generation_id"],
                action_type=kwargs["action_type"],
                publication_scope="private",
                is_public_feed=False,
                is_profile_visible=False,
                feed_prompt_visible=False,
                feed_references_visible=False,
            )
            target_session.add(generation)
            await target_session.flush()
            return generation

        monkeypatch.setattr("app.services.feed_remix.GenerationService.create", classmethod(fake_create))
        monkeypatch.setattr("app.services.feed_remix.GenerationService.wake", classmethod(_noop_wake))
        try:
            generation = await FeedRemixService.launch(
                session,
                object(),  # type: ignore[arg-type]
                source_generation_id=source.id,
                remix_author_id=remixer.id,
                surface="feed",
                prompt_override=None,
                reference_ids=[viewer_photo.id],
                confirm_own_references=True,
            )

            prompt = str(captured["prompt"])
            parameters = captured["parameters"]
            assert "@Video1" in prompt
            assert "authoritative source" in prompt
            assert "@Image1" in prompt
            assert "identity" in prompt
            assert parameters["reference_images"] == [
                "https://example.invalid/viewer-identity.jpg"
            ]
            assert parameters["reference_videos"] == [author_video]
            assert "omni_reference_task_type" not in parameters
            assert "author-identity.jpg" not in str(parameters)
            assert (generation.parameters or {})[PRIVATE_AUTHOR_REPLAY_MARKER] is True
        finally:
            target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_seedance_photo_fallback_never_submits_rendered_video(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([author, remixer])
        await session.flush()
        source, target = await _public_seedance_source(
            session,
            author=author,
            author_video=None,
        )
        viewer_photo, _ = await ReferenceService.register(
            session,
            user_id=remixer.id,
            source_url="https://example.invalid/viewer-fallback.jpg",
            kind="image",
            source="test",
        )
        captured: dict[str, object] = {}

        async def fake_create(_cls, target_session, _redis, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            generation = Generation(
                user_id=kwargs["user_id"], kind="reference_to_video", status="queued",
                prompt=kwargs["prompt"], input_url=None, cost_rox=Decimal("70.00"),
                provider="neironych", parameters={"_model_id": kwargs["model_id"], **kwargs["parameters"]},
                source_feed_gen_id=kwargs["source_feed_gen_id"],
                parent_generation_id=kwargs["parent_generation_id"], action_type="remix",
                publication_scope="private", is_public_feed=False, is_profile_visible=False,
                feed_prompt_visible=False, feed_references_visible=False,
            )
            target_session.add(generation)
            await target_session.flush()
            return generation

        monkeypatch.setattr("app.services.feed_remix.GenerationService.create", classmethod(fake_create))
        monkeypatch.setattr("app.services.feed_remix.GenerationService.wake", classmethod(_noop_wake))
        try:
            prepared = await FeedRemixService.prepare(
                session,
                source_generation_id=source.id,
                viewer_user_id=remixer.id,
                surface="feed",
            )
            assert prepared["source_has_video_reference"] is False
            generation = await FeedRemixService.launch(
                session,
                object(),  # type: ignore[arg-type]
                source_generation_id=source.id,
                remix_author_id=remixer.id,
                surface="feed",
                prompt_override=None,
                reference_ids=[viewer_photo.id],
                confirm_own_references=True,
            )
            assert captured["prompt"] == "author seedance prompt"
            assert captured["parameters"]["reference_images"] == [
                "https://example.invalid/viewer-fallback.jpg"
            ]
            assert not captured["parameters"].get("reference_videos")
            assert str(source.result_url) not in str(captured)
            assert (generation.parameters or {})[PRIVATE_AUTHOR_REPLAY_MARKER] is True
        finally:
            target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_seedance_author_recipe_rejects_viewer_video_reference() -> None:
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Author")
        remixer = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([author, remixer])
        await session.flush()
        source, target = await _public_seedance_source(
            session,
            author=author,
            author_video="https://example.invalid/author-motion.mp4",
        )
        viewer_photo, _ = await ReferenceService.register(
            session,
            user_id=remixer.id,
            source_url="https://example.invalid/viewer-identity.jpg",
            kind="image",
            source="test",
        )
        viewer_video, _ = await ReferenceService.register(
            session,
            user_id=remixer.id,
            source_url="https://example.invalid/viewer-motion.mp4",
            kind="video",
            source="test",
        )
        try:
            with pytest.raises(FeedRemixReferenceError, match="photo"):
                await FeedRemixService.quote(
                    session,
                    source_generation_id=source.id,
                    remix_author_id=remixer.id,
                    surface="feed",
                    prompt_override=None,
                    reference_ids=[viewer_photo.id, viewer_video.id],
                    confirm_own_references=True,
                )
        finally:
            target.unlink(missing_ok=True)
