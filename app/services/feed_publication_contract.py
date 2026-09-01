from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError
from app.services.reference_static import ReferenceStaticStorage

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

    from app.db.media_models import MediaAsset
    from app.db.models import Generation
    from app.services.feed import (
        FeedDerivativePublicationError,
        FeedMediaUnavailableError,
        FeedNotFoundError,
        FeedPublicationError,
        FeedService,
    )
    from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured

    previous_provider_result_urls = FeedService._provider_result_urls
    previous_to_card = FeedService.to_card

    @staticmethod
    def provider_result_urls(generation: Generation) -> list[str]:
        params = dict(generation.parameters or {})
        preserved = params.get("_provider_result_urls")
        values = [str(item) for item in preserved] if isinstance(preserved, list) else []
        for url in previous_provider_result_urls(generation):
            if url not in values:
                values.append(url)
        return [
            item
            for item in values
            if item.startswith("https://") and not FeedStaticStorage.is_local_url(item)
        ]

    async def owned_media_urls(session, generation: Generation) -> list[str]:  # type: ignore[no-untyped-def]
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
        if not assets:
            return []
        try:
            storage = ObjectStorage()
        except ObjectStorageNotConfigured:
            return []
        urls: list[str] = []
        for asset in assets:
            if not asset.object_key or not asset.bucket:
                continue
            try:
                url = storage.presign_get(key=asset.object_key, bucket=asset.bucket)
            except Exception:
                continue
            if url.startswith("https://"):
                urls.append(url)
        return urls

    @staticmethod
    def static_ready_condition() -> Any:
        prefix = FeedStaticStorage.public_prefix().replace("%", "\\%").replace("_", "\\_")
        # Production rows use PUBLIC_BASE_URL + /uploads/feed/... like tanyapi;
        # tests/local development may use the relative path when no public base is configured.
        return Generation.result_url.like(f"%{prefix}/%", escape="\\")

    @staticmethod
    async def has_static_media(session, generation_id: uuid.UUID) -> bool:  # type: ignore[no-untyped-def]
        generation = await session.get(Generation, generation_id)
        if generation is None:
            return False
        urls = _local_result_urls(generation)
        return bool(urls) and all(FeedStaticStorage.local_url_exists(url) for url in urls)

    @staticmethod
    async def static_media_views(
        session,
        generation: Generation,
        *,
        prefetched_assets: Any | None = None,
    ) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        del session, prefetched_assets
        views: list[dict[str, Any]] = []
        for ordinal, url in enumerate(_local_result_urls(generation)):
            view = FeedStaticStorage.media_view(url, ordinal=ordinal)
            if view is None:
                return []
            preview = FeedPreviewService.preview_url_for(url)
            if preview:
                view["preview_url"] = preview
            views.append(view)
        return views

    @classmethod
    def durable_references(cls, generation: Generation) -> tuple[list[str], list[str]]:
        params = dict(generation.parameters or {})
        images: list[str] = []
        videos: list[str] = []
        image_keys = tuple(
            dict.fromkeys(
                (
                    *cls.REFERENCE_IMAGE_KEYS,
                    "reference_image",
                    "reference_image_url",
                    "reference_image_urls",
                    "reference_images",
                    "image_reference_urls",
                )
            )
        )
        video_keys = tuple(
            dict.fromkeys(
                (
                    *cls.REFERENCE_VIDEO_KEYS,
                    "reference_video",
                    "reference_video_url",
                    "reference_video_urls",
                    "reference_videos",
                    "video_reference_urls",
                    "first_clip_url",
                )
            )
        )

        def accepted(value: str) -> bool:
            return (
                value.startswith("https://")
                or ReferenceStaticStorage.is_local_url(value)
                or FeedStaticStorage.is_local_url(value)
            )

        for key in image_keys:
            value = params.get(key)
            if isinstance(value, str) and accepted(value):
                images.append(value)
            elif isinstance(value, list):
                images.extend(str(item) for item in value if accepted(str(item)))
        for key in video_keys:
            value = params.get(key)
            if isinstance(value, str) and accepted(value):
                videos.append(value)
            elif isinstance(value, list):
                videos.extend(str(item) for item in value if accepted(str(item)))
        if generation.input_url and accepted(str(generation.input_url)):
            images.append(str(generation.input_url))
        return list(dict.fromkeys(images)), list(dict.fromkeys(videos))

    @classmethod
    async def card_with_preview(
        cls,
        session,
        generation: Generation,
        *,
        viewer_user_id: uuid.UUID,
        surface: str,
        prefetched: Any | None = None,
    ) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        card = await previous_to_card(
            session,
            generation,
            viewer_user_id=viewer_user_id,
            surface=surface,
            prefetched=prefetched,
        )
        media = card.get("media")
        if isinstance(media, list) and media:
            first = media[0] if isinstance(media[0], dict) else {}
            preview = first.get("preview_url")
            if isinstance(preview, str) and preview:
                card["preview_url"] = preview
        return card

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
        provider_urls = provider_result_urls(generation)
        current_local = _local_result_urls(generation)
        persisted = None

        if current_local and all(FeedStaticStorage.local_url_exists(url) for url in current_local):
            try:
                persisted = await FeedStaticStorage.persist_urls(
                    current_local,
                    generation_id=generation.id,
                )
            except FeedStaticStorageError:
                persisted = None

        if persisted is None and provider_urls:
            try:
                persisted = await FeedStaticStorage.persist_urls(
                    provider_urls,
                    generation_id=generation.id,
                )
            except FeedStaticStorageError:
                persisted = None

        if persisted is None:
            owned_urls = await owned_media_urls(session, generation)
            if owned_urls:
                try:
                    persisted = await FeedStaticStorage.persist_urls(
                        owned_urls,
                        generation_id=generation.id,
                    )
                except FeedStaticStorageError:
                    persisted = None

        if not persisted:
            raise FeedMediaUnavailableError(
                "Не удалось сохранить медиа публикации на сервере"
            )

        public_urls = [item.public_url for item in persisted]
        for url in public_urls:
            FeedPreviewService.preview_url_for(url)
        if provider_urls:
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
    FeedService._references = durable_references
    FeedService.to_card = card_with_preview
    FeedService.share_to_feed = share_to_static_feed


def _local_result_urls(generation: Any) -> list[str]:
    params = dict(generation.parameters or {})
    raw = params.get("_result_urls")
    values = [str(item) for item in raw] if isinstance(raw, list) else []
    if generation.result_url and generation.result_url not in values:
        values.insert(0, str(generation.result_url))
    return [item for item in values if FeedStaticStorage.is_local_url(item)]
