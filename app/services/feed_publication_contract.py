from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError

_INSTALLED = False


def install_feed_publication_contract() -> None:
    """Make public/profile publications depend on durable server static media.

    ``banano_kling:tanyapi`` treats provider URLs as import sources only and
    persists public feed media under ``static/uploads/feed``. ROXY follows the
    same contract here: a publication is not made visible until every result has
    been localized successfully. Feed cards never fall back to a provider URL.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.db.models import Generation
    from app.services.feed import (
        FeedDerivativePublicationError,
        FeedMediaUnavailableError,
        FeedNotFoundError,
        FeedPublicationError,
        FeedService,
    )

    previous_provider_result_urls = FeedService._provider_result_urls

    @staticmethod
    def provider_result_urls(generation: Generation) -> list[str]:
        params = dict(generation.parameters or {})
        preserved = params.get("_provider_result_urls")
        values = [str(item) for item in preserved] if isinstance(preserved, list) else []
        for url in previous_provider_result_urls(generation):
            if url not in values:
                values.append(url)
        return [item for item in values if item.startswith("https://")]

    @staticmethod
    def static_ready_condition() -> Any:
        prefix = FeedStaticStorage.public_prefix().replace("%", "\\%").replace("_", "\\_")
        return Generation.result_url.like(f"{prefix}/%", escape="\\")

    @staticmethod
    async def has_static_media(session, generation_id: uuid.UUID) -> bool:  # type: ignore[no-untyped-def]
        generation = await session.get(Generation, generation_id)
        if generation is None:
            return False
        urls = _local_result_urls(generation)
        return bool(urls) and all(FeedStaticStorage.local_url_exists(url) for url in urls)

    @staticmethod
    async def static_media_views(session, generation: Generation) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        del session
        views: list[dict[str, Any]] = []
        for ordinal, url in enumerate(_local_result_urls(generation)):
            view = FeedStaticStorage.media_view(url, ordinal=ordinal)
            if view is None:
                return []
            views.append(view)
        return views

    @classmethod
    async def share_to_static_feed(
        cls,
        session,
        *,
        generation_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        publication_scope: str,
        prompt_visible: bool = False,
        references_visible: bool = False,
    ) -> Generation:  # type: ignore[no-untyped-def]
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
        if generation.source_feed_gen_id is not None and publication_scope == "feed":
            raise FeedDerivativePublicationError(
                "Derivative generations cannot be published to feed"
            )

        params = dict(generation.parameters or {})
        current_local = _local_result_urls(generation)
        if current_local and all(FeedStaticStorage.local_url_exists(url) for url in current_local):
            sources = current_local
        else:
            sources = provider_result_urls(generation)
        if not sources:
            raise FeedMediaUnavailableError("Generation media is not ready for publication")

        try:
            persisted = await FeedStaticStorage.persist_urls(
                sources,
                generation_id=generation.id,
            )
        except FeedStaticStorageError as exc:
            raise FeedMediaUnavailableError(
                "Не удалось сохранить медиа публикации на сервере"
            ) from exc
        if not persisted:
            raise FeedMediaUnavailableError("Generation media is not ready for publication")

        public_urls = [item.public_url for item in persisted]
        provider_urls = provider_result_urls(generation)
        if provider_urls and not isinstance(params.get("_provider_result_urls"), list):
            params["_provider_result_urls"] = provider_urls
        params["_result_urls"] = public_urls
        params["_feed_static"] = True
        generation.parameters = params
        generation.result_url = public_urls[0]

        scope = publication_scope
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

    FeedService._provider_result_urls = provider_result_urls
    FeedService._ready_media_condition = static_ready_condition
    FeedService._has_ready_media = has_static_media
    FeedService._media_views = static_media_views
    FeedService.share_to_feed = share_to_static_feed


def _local_result_urls(generation: Any) -> list[str]:
    params = dict(generation.parameters or {})
    raw = params.get("_result_urls")
    values = [str(item) for item in raw] if isinstance(raw, list) else []
    if generation.result_url and generation.result_url not in values:
        values.insert(0, str(generation.result_url))
    return [item for item in values if FeedStaticStorage.is_local_url(item)]
