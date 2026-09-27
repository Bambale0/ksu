from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.models import Generation
from app.db.session import SessionFactory
from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage, PersistedFeedMedia


async def backfill(*, apply: bool, backup_path: Path | None, limit: int | None) -> None:
    if apply and backup_path is None:
        raise ValueError("--backup-path is required with --apply")
    backup = None
    if apply and backup_path is not None:
        descriptor = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        backup = os.fdopen(descriptor, "w", encoding="utf-8")
    scanned = prepared = already_ready = failed = 0
    try:
        async with SessionFactory() as session:
            statement = (
                select(Generation.id)
                .where(
                    Generation.status == "succeeded",
                    Generation.is_public_feed.is_(True),
                    Generation.result_url.ilike("%.mp4"),
                )
                .order_by(Generation.feed_published_at.asc())
            )
            if limit is not None:
                statement = statement.limit(limit)
            generation_ids = list((await session.scalars(statement)).all())

        for generation_id in generation_ids:
            scanned += 1
            try:
                async with SessionFactory() as session:
                    generation = await session.scalar(
                        select(Generation).where(Generation.id == generation_id).with_for_update()
                    )
                    if generation is None or not generation.result_url:
                        raise ValueError("Generation is unavailable")
                    old_url = generation.result_url
                    source = FeedStaticStorage.path_for_url(old_url)
                    if source is None or not source.is_file():
                        raise ValueError("Feed video is missing")
                    if FeedStaticStorage.mp4_has_faststart(source):
                        already_ready += 1
                        continue
                    params = dict(generation.parameters or {})
                    urls = params.get("_result_urls")
                    if not isinstance(urls, list) or urls != [old_url]:
                        raise ValueError("Expected one feed video matching result_url")
                    if not apply:
                        prepared += 1
                        continue
                    suffix, content_type, size, digest = FeedStaticStorage._inspect_file(source)
                    item = PersistedFeedMedia(
                        public_url=old_url, path=source, content_type=content_type,
                        size_bytes=size, sha256=digest, ordinal=0,
                    )
                    optimized = await asyncio.to_thread(
                        FeedStaticStorage.faststart_copy, item, generation_id=generation.id
                    )
                    poster = await asyncio.to_thread(
                        FeedPreviewService.preview_url_for, optimized.public_url
                    )
                    if poster is None:
                        raise ValueError("Prepared feed video has no poster")
                    assert backup is not None
                    backup.write(json.dumps({
                        "id": str(generation.id), "old_url": old_url,
                        "new_url": optimized.public_url,
                    }) + "\n")
                    backup.flush()
                    os.fsync(backup.fileno())
                    params["_result_urls"] = [optimized.public_url]
                    generation.parameters = params
                    generation.result_url = optimized.public_url
                    await session.commit()
                    prepared += 1
            except Exception as exc:
                failed += 1
                print(f"feed-faststart failed generation={generation_id}: {exc}")
    finally:
        if backup is not None:
            backup.close()
    print(
        f"feed-faststart scanned={scanned} {'updated' if apply else 'would_update'}={prepared} "
        f"already_ready={already_ready} failed={failed}"
    )
    if failed:
        raise SystemExit(1)


async def restore(backup_path: Path) -> None:
    rows = [json.loads(line) for line in backup_path.read_text(encoding="utf-8").splitlines()]
    restored = skipped = 0
    for row in rows:
        async with SessionFactory() as session:
            generation = await session.scalar(
                select(Generation).where(Generation.id == uuid.UUID(row["id"])).with_for_update()
            )
            if generation is None or generation.result_url != row["new_url"]:
                skipped += 1
                continue
            params = dict(generation.parameters or {})
            if params.get("_result_urls") != [row["new_url"]]:
                skipped += 1
                continue
            params["_result_urls"] = [row["old_url"]]
            generation.parameters = params
            generation.result_url = row["old_url"]
            await session.commit()
            restored += 1
    print(f"feed-faststart restored={restored} skipped={skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make published feed MP4s start before full download")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--restore-from", type=Path)
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.restore_from:
        asyncio.run(restore(args.restore_from))
    else:
        asyncio.run(backfill(apply=args.apply, backup_path=args.backup_path, limit=args.limit))


if __name__ == "__main__":
    main()
