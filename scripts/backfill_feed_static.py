from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.db.session import SessionFactory
from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured


@dataclass(slots=True)
class BackfillStats:
    scanned: int = 0
    already_static: int = 0
    localized: int = 0
    failed: int = 0


def _local_urls(generation: Generation) -> list[str]:
    params = dict(generation.parameters or {})
    raw = params.get("_result_urls")
    values = [str(item) for item in raw] if isinstance(raw, list) else []
    if generation.result_url and generation.result_url not in values:
        values.insert(0, str(generation.result_url))
    return [item for item in values if FeedStaticStorage.is_local_url(item)]


def _provider_urls(generation: Generation) -> list[str]:
    params = dict(generation.parameters or {})
    values: list[str] = []
    for key in ("_provider_result_urls", "_result_urls"):
        raw = params.get(key)
        if isinstance(raw, list):
            for item in raw:
                value = str(item)
                if (
                    value.startswith("https://")
                    and not FeedStaticStorage.is_local_url(value)
                    and value not in values
                ):
                    values.append(value)
    if generation.result_url and generation.result_url.startswith("https://"):
        if (
            not FeedStaticStorage.is_local_url(generation.result_url)
            and generation.result_url not in values
        ):
            values.insert(0, generation.result_url)
    return values


def _ensure_previews(urls: list[str]) -> None:
    for url in urls:
        FeedPreviewService.preview_url_for(url)


async def _s3_urls(session, generation: Generation) -> list[str]:  # type: ignore[no-untyped-def]
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
            urls.append(storage.presign_get(key=asset.object_key, bucket=asset.bucket))
        except Exception:
            continue
    return urls


async def _persist_generation(session, generation: Generation) -> bool:  # type: ignore[no-untyped-def]
    local = _local_urls(generation)
    if local and all(FeedStaticStorage.local_url_exists(url) for url in local):
        _ensure_previews(local)
        return False

    provider_sources = _provider_urls(generation)
    candidates = provider_sources
    try:
        if not candidates:
            raise FeedStaticStorageError("no provider URLs")
        persisted = await FeedStaticStorage.persist_urls(
            candidates,
            generation_id=generation.id,
        )
    except FeedStaticStorageError:
        candidates = await _s3_urls(session, generation)
        if not candidates:
            raise
        persisted = await FeedStaticStorage.persist_urls(
            candidates,
            generation_id=generation.id,
        )

    public_urls = [item.public_url for item in persisted]
    _ensure_previews(public_urls)
    params = dict(generation.parameters or {})
    if provider_sources:
        params["_provider_result_urls"] = provider_sources
    params["_result_urls"] = public_urls
    params["_feed_static"] = True
    generation.parameters = params
    generation.result_url = public_urls[0]
    await session.commit()
    return True


async def backfill(*, limit: int | None = None, strict: bool = False) -> BackfillStats:
    stats = BackfillStats()
    FeedStaticStorage.ensure_root()
    async with SessionFactory() as session:
        stmt = (
            select(Generation)
            .where(
                Generation.status == "succeeded",
                Generation.publication_scope.in_(("feed", "profile")),
                Generation.is_profile_visible.is_(True),
            )
            .order_by(Generation.feed_published_at.asc().nullsfirst(), Generation.created_at.asc())
        )
        if limit is not None:
            stmt = stmt.limit(max(1, limit))
        generations = list((await session.scalars(stmt)).all())
        for generation in generations:
            generation_id = generation.id
            stats.scanned += 1
            try:
                changed = await _persist_generation(session, generation)
            except Exception as exc:
                await session.rollback()
                stats.failed += 1
                print(f"feed-static backfill failed generation={generation_id}: {exc}")
                if strict:
                    raise
            else:
                if changed:
                    stats.localized += 1
                else:
                    stats.already_static += 1

    print(
        "feed-static backfill "
        f"scanned={stats.scanned} localized={stats.localized} "
        f"already_static={stats.already_static} failed={stats.failed}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist existing ROXY feed/profile media into static/uploads/feed"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill(limit=args.limit, strict=args.strict))


if __name__ == "__main__":
    main()
