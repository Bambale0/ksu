from __future__ import annotations

import random
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.feed_models import FeedRemixEvent
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_static import FeedStaticStorage


def _telegram_id() -> int:
    return random.randint(9_000_000_000_000, 9_899_999_999_999)


@pytest.mark.asyncio
async def test_remix_restores_prompt_server_side_and_records_lineage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async with SessionFactory() as session:
        source_author = User(telegram_id=_telegram_id(), first_name="Source")
        remix_author = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add_all([source_author, remix_author])
        await session.flush()
        provider_url = "https://example.invalid/source.png"
        source = Generation(
            user_id=source_author.id,
            kind="text_to_image",
            status="succeeded",
            prompt="server-only prompt",
            input_url="https://example.invalid/reference.png",
            result_url=provider_url,
            cost_rox=Decimal("8.00"),
            provider="kie",
            parameters={
                "_model_id": "nano-banana-2",
                "_billing_seconds": None,
                "image_url": "https://example.invalid/reference.png",
            },
            publication_scope="feed",
            is_public_feed=True,
            is_profile_visible=True,
            feed_prompt_visible=False,
            feed_references_visible=False,
        )
        session.add(source)
        await session.flush()
        filename = f"test-remix-{source.id}.png"
        (FeedStaticStorage.ensure_root() / filename).write_bytes(
            b"\x89PNG\r\n\x1a\nroxy-feed-remix-fixture"
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
                user_id=source_author.id,
                ordinal=0,
                source_url=provider_url,
                status="ready",
                bucket="test-feed",
                object_key=f"feed/{source.id}.png",
                content_type="image/png",
            )
        )
        await session.commit()

        captured = {}

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
                    "parameters": parameters,
                    "billing_seconds": billing_seconds,
                    "source_feed_gen_id": source_feed_gen_id,
                    "parent_generation_id": parent_generation_id,
                    "action_type": action_type,
                }
            )
            generation = Generation(
                user_id=user_id,
                kind="text_to_image",
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

        monkeypatch.setattr("app.services.feed.GenerationService.create", classmethod(fake_create))
        generation = await FeedService.remix(
            session,
            object(),  # type: ignore[arg-type]
            source_generation_id=source.id,
            remix_author_id=remix_author.id,
            surface="feed",
        )

        assert captured["prompt"] == "server-only prompt"
        assert captured["source_feed_gen_id"] == source.id
        assert captured["parent_generation_id"] == source.id
        assert captured["action_type"] == "remix"
        assert generation.source_feed_gen_id == source.id
        assert generation.publication_scope == "private"
        event = await session.scalar(
            select(FeedRemixEvent).where(FeedRemixEvent.remix_generation_id == generation.id)
        )
        assert event is not None
        assert event.source_generation_id == source.id
        assert event.source_author_id == source_author.id
        assert event.remix_author_id == remix_author.id


@pytest.mark.asyncio
async def test_private_generation_cannot_be_opened_or_remixed_by_id() -> None:
    async with SessionFactory() as session:
        author = User(telegram_id=_telegram_id(), first_name="Private")
        viewer = User(telegram_id=_telegram_id(), first_name="Viewer")
        session.add_all([author, viewer])
        await session.flush()
        private = Generation(
            user_id=author.id,
            kind="text_to_image",
            status="succeeded",
            prompt="private prompt",
            result_url="https://example.invalid/private.png",
            cost_rox=Decimal("1.00"),
            provider="kie",
            parameters={"_model_id": "nano-banana-2"},
            publication_scope="private",
            is_public_feed=False,
            is_profile_visible=False,
        )
        session.add(private)
        await session.flush()
        session.add(
            MediaAsset(
                generation_id=private.id,
                user_id=author.id,
                ordinal=0,
                source_url=private.result_url,
                status="ready",
                bucket="test-feed",
                object_key=f"feed/{private.id}.png",
                content_type="image/png",
            )
        )
        await session.commit()
        with pytest.raises(FeedNotFoundError):
            await FeedService.get_feed_generation_card(
                session,
                generation_id=private.id,
                viewer_user_id=viewer.id,
            )
        with pytest.raises(FeedNotFoundError):
            await FeedService.get_profile_generation_card(
                session,
                generation_id=private.id,
                viewer_user_id=viewer.id,
            )
