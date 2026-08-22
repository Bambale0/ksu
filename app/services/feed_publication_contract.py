from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

_INSTALLED = False


def install_feed_publication_contract() -> None:
    """Keep publishing usable while owned-media ingest is still catching up.

    Feed cards already know how to fall back to the provider result URL when an
    owned S3 asset is not ready yet. The discovery predicates and visibility
    guard were stricter than the card renderer, which made a successful publish
    disappear from the feed until the asynchronous media worker completed.

    A completed generation with a provider HTTPS result is therefore publishable
    immediately; owned media remains preferred automatically as soon as ingest
    finishes.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.db.models import Generation
    from app.services.feed import FeedService

    previous_ready_condition = FeedService._ready_media_condition
    previous_has_ready_media = FeedService._has_ready_media

    @staticmethod
    def publishable_media_condition() -> Any:
        return or_(
            previous_ready_condition(),
            Generation.result_url.is_not(None),
        )

    @staticmethod
    async def has_publishable_media(session, generation_id) -> bool:  # type: ignore[no-untyped-def]
        if await previous_has_ready_media(session, generation_id):
            return True
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id)
        )
        if generation is None:
            return False
        return bool(FeedService._provider_result_urls(generation))

    FeedService._ready_media_condition = publishable_media_condition
    FeedService._has_ready_media = has_publishable_media
