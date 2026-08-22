from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.services.media_assets import MediaIngestError, MediaIngestService, UnsafeMediaSource

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_DEFAULT_MAX_BYTES = 200 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 180.0
_DEFAULT_MAX_REDIRECTS = 3


class FeedStaticStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PersistedFeedMedia:
    public_url: str
    path: Path
    content_type: str
    size_bytes: int
    sha256: str
    ordinal: int


class FeedStaticStorage:
    """Persist published feed media under the backend static tree.

    This mirrors the proven ``banano_kling:tanyapi`` feed persistence contract:
    provider URLs are import sources only. Once a generation is published, feed
    cards use immutable server-owned files under ``static/uploads/feed``.
    """

    @staticmethod
    def root() -> Path:
        return Path(os.getenv("FEED_STATIC_ROOT", "static/uploads/feed")).resolve()

    @staticmethod
    def public_prefix() -> str:
        value = os.getenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed").strip()
        value = "/" + value.strip("/")
        return value.rstrip("/")

    @classmethod
    def public_url_for(cls, filename: str) -> str:
        relative = f"{cls.public_prefix()}/{filename.lstrip('/')}"
        base = settings.public_base_url.strip().rstrip("/")
        return f"{base}{relative}" if base else relative

    @staticmethod
    def max_bytes() -> int:
        raw = os.getenv("FEED_STATIC_MAX_BYTES", str(_DEFAULT_MAX_BYTES))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_BYTES
        return max(1, value)

    @staticmethod
    def timeout_seconds() -> float:
        raw = os.getenv("FEED_STATIC_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return _DEFAULT_TIMEOUT_SECONDS
        return max(5.0, value)

    @staticmethod
    def max_redirects() -> int:
        raw = os.getenv("FEED_STATIC_MAX_REDIRECTS", str(_DEFAULT_MAX_REDIRECTS))
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_REDIRECTS
        return max(0, min(value, 10))

    @classmethod
    def ensure_root(cls) -> Path:
        root = cls.root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def is_local_url(cls, value: str | None) -> bool:
        if not value:
            return False
        parsed = urlparse(value)
        path = parsed.path if parsed.scheme else value.split("?", 1)[0]
        prefix = cls.public_prefix() + "/"
        return path.startswith(prefix)

    @classmethod
    def path_for_url(cls, value: str) -> Path | None:
        if not cls.is_local_url(value):
            return None
        parsed = urlparse(value)
        path = parsed.path if parsed.scheme else value.split("?", 1)[0]
        prefix = cls.public_prefix() + "/"
        relative = path[len(prefix) :]
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            return None
        root = cls.root()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    @classmethod
    def local_url_exists(cls, value: str | None) -> bool:
        if not value:
            return False
        path = cls.path_for_url(value)
        if path is None:
            return False
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    @staticmethod
    def _magic(data: bytes) -> tuple[str, str] | None:
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg", "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png", "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif", "image/gif"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp", "image/webp"
        if len(data) >= 12 and data[4:8] == b"ftyp":
            return ".mp4", "video/mp4"
        if data.startswith(b"\x1aE\xdf\xa3"):
            return ".webm", "video/webm"
        return None

    @classmethod
    def _inspect_file(cls, path: Path) -> tuple[str, str, int, str]:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise FeedStaticStorageError("Feed media file is unavailable") from exc
        if size <= 0:
            raise FeedStaticStorageError("Feed media file is empty")
        if size > cls.max_bytes():
            raise FeedStaticStorageError("Feed media exceeds FEED_STATIC_MAX_BYTES")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            first = handle.read(64)
            digest.update(first)
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        detected = cls._magic(first)
        if detected is None:
            raise FeedStaticStorageError("Unsupported or invalid feed media file")
        suffix, content_type = detected
        return suffix, content_type, size, digest.hexdigest()

    @classmethod
    async def _download_external(cls, source_url: str) -> tuple[Path, str, str, int, str]:
        current_url = source_url
        root = cls.ensure_root()
        timeout = httpx.Timeout(
            connect=min(30.0, cls.timeout_seconds()),
            read=cls.timeout_seconds(),
            write=30.0,
            pool=30.0,
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "roxy-feed-persist/1.0"},
        ) as client:
            for _ in range(cls.max_redirects() + 1):
                try:
                    await MediaIngestService._validate_public_https_url(current_url)
                except UnsafeMediaSource as exc:
                    raise FeedStaticStorageError(str(exc)) from exc
                try:
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in _REDIRECT_CODES:
                            location = response.headers.get("location")
                            if not location:
                                raise FeedStaticStorageError(
                                    "Feed media redirect has no Location header"
                                )
                            current_url = urljoin(current_url, location)
                            continue
                        response.raise_for_status()
                        declared = response.headers.get("content-length")
                        if declared:
                            try:
                                declared_size = int(declared)
                            except ValueError as exc:
                                raise FeedStaticStorageError(
                                    "Feed media returned invalid Content-Length"
                                ) from exc
                            if declared_size > cls.max_bytes():
                                raise FeedStaticStorageError(
                                    "Feed media exceeds FEED_STATIC_MAX_BYTES"
                                )

                        handle = tempfile.NamedTemporaryFile(
                            prefix=".roxy-feed-",
                            suffix=".part",
                            dir=root,
                            delete=False,
                        )
                        temp_path = Path(handle.name)
                        size = 0
                        digest = hashlib.sha256()
                        first = bytearray()
                        try:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                size += len(chunk)
                                if size > cls.max_bytes():
                                    raise FeedStaticStorageError(
                                        "Feed media exceeds FEED_STATIC_MAX_BYTES"
                                    )
                                if len(first) < 64:
                                    first.extend(chunk[: 64 - len(first)])
                                digest.update(chunk)
                                handle.write(chunk)
                        except Exception:
                            handle.close()
                            temp_path.unlink(missing_ok=True)
                            raise
                        handle.close()
                        if size <= 0:
                            temp_path.unlink(missing_ok=True)
                            raise FeedStaticStorageError("Feed media is empty")
                        detected = cls._magic(bytes(first))
                        if detected is None:
                            temp_path.unlink(missing_ok=True)
                            raise FeedStaticStorageError(
                                "Unsupported or invalid feed media payload"
                            )
                        suffix, content_type = detected
                        return temp_path, suffix, content_type, size, digest.hexdigest()
                except FeedStaticStorageError:
                    raise
                except (httpx.HTTPError, MediaIngestError) as exc:
                    raise FeedStaticStorageError(f"Failed to download feed media: {exc}") from exc
            raise FeedStaticStorageError("Too many feed media redirects")

    @classmethod
    async def _persist_one(
        cls,
        source_url: str,
        *,
        generation_id: uuid.UUID,
        ordinal: int,
    ) -> tuple[PersistedFeedMedia, bool]:
        if cls.is_local_url(source_url):
            existing = cls.path_for_url(source_url)
            if existing is None or not existing.is_file():
                raise FeedStaticStorageError("Stored feed media is missing")
            _suffix, content_type, size, digest = cls._inspect_file(existing)
            return (
                PersistedFeedMedia(
                    public_url=cls.public_url_for(existing.name),
                    path=existing,
                    content_type=content_type,
                    size_bytes=size,
                    sha256=digest,
                    ordinal=ordinal,
                ),
                False,
            )

        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise FeedStaticStorageError("Feed media source must be a public HTTPS URL")

        temp_path, suffix, content_type, size, digest = await cls._download_external(source_url)
        filename = f"{generation_id}-{ordinal + 1}-{digest[:16]}{suffix}"
        target = cls.ensure_root() / filename
        created = False
        try:
            if target.exists():
                existing_suffix, existing_type, existing_size, existing_digest = cls._inspect_file(target)
                if existing_digest != digest or existing_size != size or existing_suffix != suffix:
                    raise FeedStaticStorageError("Static feed media collision detected")
                content_type = existing_type
            else:
                os.replace(temp_path, target)
                created = True
            return (
                PersistedFeedMedia(
                    public_url=cls.public_url_for(filename),
                    path=target,
                    content_type=content_type,
                    size_bytes=size,
                    sha256=digest,
                    ordinal=ordinal,
                ),
                created,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @classmethod
    async def persist_urls(
        cls,
        urls: list[str],
        *,
        generation_id: uuid.UUID,
    ) -> list[PersistedFeedMedia]:
        unique = list(dict.fromkeys(str(item).strip() for item in urls if str(item).strip()))
        if not unique:
            raise FeedStaticStorageError("Generation has no media to publish")

        persisted: list[PersistedFeedMedia] = []
        created_paths: list[Path] = []
        try:
            for ordinal, source_url in enumerate(unique):
                item, created = await cls._persist_one(
                    source_url,
                    generation_id=generation_id,
                    ordinal=ordinal,
                )
                persisted.append(item)
                if created:
                    created_paths.append(item.path)
        except Exception:
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise
        return persisted

    @classmethod
    def media_view(cls, url: str, *, ordinal: int) -> dict[str, object] | None:
        path = cls.path_for_url(url)
        if path is None or not path.is_file():
            return None
        try:
            _suffix, content_type, size, _digest = cls._inspect_file(path)
        except FeedStaticStorageError:
            return None
        public_url = cls.public_url_for(path.name)
        return {
            "id": None,
            "url": public_url,
            "download_url": public_url,
            "public_url": public_url,
            "content_type": content_type,
            "size_bytes": size,
            "ordinal": ordinal,
            "storage": "static",
        }
