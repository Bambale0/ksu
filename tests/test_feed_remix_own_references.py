from __future__ import annotations

import random
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.feed_models import FeedRemixEvent
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.feed_remix import FeedRemixReferenceError, FeedRemixService
from app.services.feed_static import FeedStaticStorage
from app.services.references import ReferenceService


def _telegram_id() -> int:
    return random.randint(9_900_000_000_000, 9_999_999_999_999)


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
        assert generation.source_feed_gen_id == source.id

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
