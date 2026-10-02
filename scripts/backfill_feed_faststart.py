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
    if limit is not None and limit <= 0:
        raise ValueError("--limit must be positive")
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
                    Generation.publication_scope.in_(("profile", "feed")),
                    Generation.is_profile_visible.is_(True),
                    Generation.result_url.ilike("%.mp4"),
                )
                .order_by(Generation.feed_published_at.asc(), Generation.id.asc())
            )
            # Limit work, not the oldest SELECT rows: otherwise later batches
            # repeatedly select only videos optimized by the first invocation.
            generation_ids = list((await session.scalars(statement)).all())

        for generation_id in generation_ids:
            if limit is not None and prepared + failed >= limit:
                break
            scanned += 1
            try:
                async with SessionFactory() as session:
                    generation = await session.scalar(
                        select(Generation).where(Generation.id == generation_id).with_for_update()
                    )
                    if generation is None or not generation.result_url:
                        raise ValueError("Generation is unavailable")
                    # Recheck visibility after acquiring the lock; a user can
                    # unpublish or hide a row after the candidate query.
                    if (generation.status != "succeeded"
                            or generation.publication_scope not in {"profile", "feed"}
                            or not generation.is_profile_visible):
                        continue
                    old_url = generation.result_url
                    params = dict(generation.parameters or {})
                    urls = params.get("_result_urls")
                    if (not isinstance(urls, list) or not urls or urls[0] != old_url
                            or not all(isinstance(url, str) for url in urls)):
                        raise ValueError("Expected a media list starting with result_url")
                    candidates: list[tuple[int, Path]] = []
                    for ordinal, url in enumerate(urls):
                        source = FeedStaticStorage.path_for_url(url)
                        if source is None or not source.is_file():
                            raise ValueError("Published media is missing")
                        if source.suffix.lower() == ".mp4" and not FeedStaticStorage.mp4_has_faststart(source):
                            candidates.append((ordinal, source))
                    if not candidates:
                        already_ready += 1
                        continue
                    if not apply:
                        prepared += 1
                        continue
                    new_urls = list(urls)
                    for ordinal, source in candidates:
                        _, content_type, size, digest = FeedStaticStorage._inspect_file(source)
                        item = PersistedFeedMedia(
                            public_url=urls[ordinal], path=source, content_type=content_type,
                            size_bytes=size, sha256=digest, ordinal=ordinal,
                        )
                        optimized = await asyncio.to_thread(
                            FeedStaticStorage.faststart_copy, item, generation_id=generation.id
                        )
                        poster = await asyncio.to_thread(
                            FeedPreviewService.preview_url_for, optimized.public_url
                        )
                        if poster is None:
                            raise ValueError("Prepared video has no poster")
                        new_urls[ordinal] = optimized.public_url
                    assert backup is not None
                    record: dict[str, object] = {"id": str(generation.id), "old_url": old_url, "new_url": new_urls[0]}
                    # Preserve compatibility with the original singleton backup.
                    if len(urls) > 1:
                        record.update(old_urls=urls, new_urls=new_urls)
                    backup.write(json.dumps(record) + "\n")
                    backup.flush()
                    os.fsync(backup.fileno())
                    params["_result_urls"] = new_urls
                    generation.parameters = params
                    generation.result_url = new_urls[0]
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
        old_urls = row.get("old_urls", [row["old_url"]])
        new_urls = row.get("new_urls", [row["new_url"]])
        if (not isinstance(old_urls, list) or not isinstance(new_urls, list)
                or not old_urls or len(old_urls) != len(new_urls)
                or old_urls[0] != row["old_url"] or new_urls[0] != row["new_url"]
                or not all(isinstance(url, str) for url in old_urls + new_urls)):
            raise ValueError("Invalid media list in backup")
        async with SessionFactory() as session:
            generation = await session.scalar(
                select(Generation).where(Generation.id == uuid.UUID(row["id"])).with_for_update()
            )
            if generation is None or generation.result_url != row["new_url"]:
                skipped += 1
                continue
            params = dict(generation.parameters or {})
            if params.get("_result_urls") != new_urls:
                skipped += 1
                continue
            params["_result_urls"] = old_urls
            generation.parameters = params
            generation.result_url = row["old_url"]
            await session.commit()
            restored += 1
    print(f"feed-faststart restored={restored} skipped={skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare published feed/profile MP4s for progressive playback")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--restore-from", type=Path)
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--limit", type=int, help="Maximum videos needing conversion, not already-ready rows")
    args = parser.parse_args()
    if args.restore_from:
        asyncio.run(restore(args.restore_from))
    else:
        asyncio.run(backfill(apply=args.apply, backup_path=args.backup_path, limit=args.limit))


if __name__ == "__main__":
    main()
