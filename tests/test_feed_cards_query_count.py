from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event

from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory, engine
from app.services.feed import FeedService
from app.services.feed_static import FeedStaticStorage


def _telegram_id() -> int:
    return random.randint(9_100_000_000_000, 9_199_999_999_999)


@pytest.mark.asyncio
async def test_feed_cards_batch_related_data_instead_of_n_plus_one() -> None:
    created_files: list[Path] = []
    async with SessionFactory() as session:
        viewer = User(telegram_id=_telegram_id(), first_name="Query Count")
        session.add(viewer)
        await session.flush()

        for index in range(24):
            filename = f"query-count-{viewer.id}-{index}.png"
            path = FeedStaticStorage.ensure_root() / filename
            path.write_bytes(b"\x89PNG\r\n\x1a\nroxy-query-count")
            created_files.append(path)
            local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"
            generation = Generation(
                user_id=viewer.id,
                kind="text_to_image",
                status="succeeded",
                prompt=f"query count {index}",
                result_url=local_url,
                cost_rox=Decimal("1.00"),
                provider="kie",
                parameters={
                    "_model_id": "nano-banana-2",
                    "_result_urls": [local_url],
                    "_feed_static": True,
                },
                publication_scope="feed",
                is_public_feed=True,
                is_profile_visible=True,
                feed_prompt_visible=False,
                feed_references_visible=False,
                feed_published_at=datetime.now(UTC),
                is_adult_content=False,
            )
            session.add(generation)
            await session.flush()
            session.add(
                MediaAsset(
                    generation_id=generation.id,
                    user_id=viewer.id,
                    ordinal=0,
                    source_url=f"https://example.invalid/{generation.id}.png",
                    status="ready",
                    bucket="test-feed",
                    object_key=f"feed/{generation.id}.png",
                    content_type="image/png",
                    size_bytes=128,
                )
            )
        await session.commit()

        generations = await FeedService.get_feed_generations(
            session,
            sort="recent",
            limit=24,
        )
        assert len(generations) >= 24
        target = generations[:24]

        statements: list[str] = []

        def count_query(_conn, _cursor, statement, _parameters, _context, _executemany):  # type: ignore[no-untyped-def]
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", count_query)
        try:
            cards = await FeedService.cards_for_generations(
                session,
                target,
                viewer_user_id=viewer.id,
                surface="feed",
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_query)
            for path in created_files:
                path.unlink(missing_ok=True)

        assert len(cards) == 24
        assert len(statements) <= 12, statements
