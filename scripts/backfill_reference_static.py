from __future__ import annotations

import argparse
import asyncio
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.media_assets import MediaIngestService, UnsafeMediaSource
from app.services.media_probe import probe_media_stream
from app.services.reference_static import ReferenceStaticStorage, ReferenceStaticStorageError

_REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass(slots=True)
class BackfillStats:
    scanned: int = 0
    already_static: int = 0
    localized: int = 0
    failed: int = 0


async def _download(source_url: str) -> tuple[Path, str, str, int, str]:
    current_url = source_url
    max_bytes = max(1, int(settings.kie_upload_max_bytes))
    timeout = httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "roxy-reference-backfill/1.0"},
    ) as client:
        for _ in range(4):
            await MediaIngestService._validate_public_https_url(current_url)
            async with client.stream("GET", current_url) as response:
                if response.status_code in _REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise ReferenceStaticStorageError(
                            "Reference redirect has no Location header"
                        )
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except ValueError as exc:
                        raise ReferenceStaticStorageError(
                            "Reference returned invalid Content-Length"
                        ) from exc
                    if declared_size > max_bytes:
                        raise ReferenceStaticStorageError("Reference exceeds upload limit")

                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                filename = Path(urlparse(current_url).path).name or "reference"
                handle = tempfile.NamedTemporaryFile(
                    prefix="roxy-reference-backfill-",
                    suffix=Path(filename).suffix or ".bin",
                    delete=False,
                )
                path = Path(handle.name)
                digest = hashlib.sha256()
                size = 0
                try:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ReferenceStaticStorageError("Reference exceeds upload limit")
                        digest.update(chunk)
                        handle.write(chunk)
                except Exception:
                    handle.close()
                    path.unlink(missing_ok=True)
                    raise
                handle.close()
                if size <= 0:
                    path.unlink(missing_ok=True)
                    raise ReferenceStaticStorageError("Reference source is empty")
                return path, filename, content_type, size, digest.hexdigest()
        raise ReferenceStaticStorageError("Too many reference redirects")


async def _persist_reference(session, row: UserReference) -> bool:  # type: ignore[no-untyped-def]
    if ReferenceStaticStorage.local_url_exists(row.source_url):
        return False
    if not row.source_url.startswith("https://"):
        raise ReferenceStaticStorageError("Legacy reference is not a public HTTPS URL")

    path, downloaded_name, downloaded_type, size, digest = await _download(row.source_url)
    try:
        duplicate = await session.scalar(
            select(UserReference).where(
                UserReference.id != row.id,
                UserReference.user_id == row.user_id,
                UserReference.kind == row.kind,
                UserReference.file_hash == digest,
                UserReference.status == "ready",
            )
        )
        if duplicate is not None:
            raise ReferenceStaticStorageError(
                f"Reference duplicates existing library item {duplicate.id}"
            )

        filename = row.original_filename or downloaded_name
        content_type = row.content_type or downloaded_type or "application/octet-stream"
        with path.open("rb") as stream:
            local_url, _target, stored_size = ReferenceStaticStorage.persist_stream(
                stream,
                user_id=row.user_id,
                kind=row.kind,
                file_hash=digest,
                filename=filename,
                content_type=content_type,
                expected_size=size,
            )
        with path.open("rb") as stream:
            probe = probe_media_stream(stream, filename)

        row.source_url = local_url
        row.file_hash = digest
        row.original_filename = filename[:255]
        row.content_type = content_type[:255]
        row.size_bytes = stored_size
        if probe.status == "ready" or row.probe_status != "ready":
            row.duration_ms = probe.duration_ms
            row.width = probe.width
            row.height = probe.height
            row.container = probe.container
            row.video_codec = probe.video_codec
            row.audio_codec = probe.audio_codec
            row.probe_status = probe.status
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            ReferenceStaticStorage.remove_url(local_url)
            raise ReferenceStaticStorageError("Reference backfill hit a duplicate row") from exc
        return True
    finally:
        path.unlink(missing_ok=True)


async def backfill(*, limit: int | None = None, strict: bool = False) -> BackfillStats:
    stats = BackfillStats()
    ReferenceStaticStorage.ensure_root()
    async with SessionFactory() as session:
        stmt = (
            select(UserReference)
            .where(UserReference.status == "ready")
            .order_by(UserReference.created_at.asc(), UserReference.id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        rows = list((await session.scalars(stmt)).all())
        for row in rows:
            reference_id = row.id
            source_url = row.source_url
            stats.scanned += 1
            if ReferenceStaticStorage.local_url_exists(source_url):
                stats.already_static += 1
                continue
            try:
                changed = await _persist_reference(session, row)
            except (ReferenceStaticStorageError, UnsafeMediaSource, httpx.HTTPError) as exc:
                await session.rollback()
                stats.failed += 1
                print(f"reference-static backfill failed reference={reference_id}: {exc}")
                if strict:
                    raise
            except Exception as exc:
                await session.rollback()
                stats.failed += 1
                print(f"reference-static backfill unexpected reference={reference_id}: {exc}")
                if strict:
                    raise
            else:
                if changed:
                    stats.localized += 1
                else:
                    stats.already_static += 1

    print(
        "reference-static backfill "
        f"scanned={stats.scanned} localized={stats.localized} "
        f"already_static={stats.already_static} failed={stats.failed}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist legacy ROXY reference URLs under static/uploads/refs"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill(limit=args.limit, strict=args.strict))


if __name__ == "__main__":
    main()
