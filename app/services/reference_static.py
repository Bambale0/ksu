from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

from app.core.config import settings


class ReferenceStaticStorageError(RuntimeError):
    pass


class ReferenceStaticStorage:
    """Durable product-owned storage for reusable reference media.

    The reference library stores these server-owned URLs as its source of truth.
    Provider URLs are transport artifacts created later, immediately before a
    generation request is submitted.

    File names are untrusted user input. Persisted extensions therefore come
    exclusively from an allow-listed media Content-Type, never from the supplied
    filename. This keeps the product origin from becoming an active-document
    hosting surface (for example ``evil.html`` declared as ``image/png``).
    """

    SAFE_MEDIA_EXTENSIONS: dict[str, str] = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "image/avif": ".avif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "video/mpeg": ".mpeg",
        "video/ogg": ".ogv",
        "video/x-m4v": ".m4v",
        "video/x-msvideo": ".avi",
        "video/x-matroska": ".mkv",
        "audio/aac": ".aac",
        "audio/aiff": ".aiff",
        "audio/x-aiff": ".aiff",
        "audio/flac": ".flac",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
    }

    @staticmethod
    def root() -> Path:
        return Path(os.getenv("REFERENCE_STATIC_ROOT", "static/uploads/refs")).resolve()

    @staticmethod
    def public_prefix() -> str:
        value = os.getenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs").strip()
        return ("/" + value.strip("/")).rstrip("/")

    @classmethod
    def public_url(cls, relative_path: str) -> str:
        path = f"{cls.public_prefix()}/{relative_path.lstrip('/')}"
        base = settings.public_base_url.strip().rstrip("/")
        return f"{base}{path}" if base else path

    @classmethod
    def ensure_root(cls) -> Path:
        root = cls.root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def is_local_url(cls, value: str | None) -> bool:
        if not value:
            return False
        parsed = urlparse(str(value))
        path = parsed.path if parsed.scheme else str(value).split("?", 1)[0]
        return path.startswith(cls.public_prefix() + "/")

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
    def _safe_kind(kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if normalized not in {"image", "video", "audio"}:
            raise ReferenceStaticStorageError("Unsupported reference kind")
        return normalized

    @classmethod
    def normalize_content_type(cls, content_type: str | None) -> str:
        return str(content_type or "").split(";", 1)[0].strip().lower()

    @classmethod
    def supports_content_type(cls, content_type: str | None, *, kind: str | None = None) -> bool:
        normalized = cls.normalize_content_type(content_type)
        if normalized not in cls.SAFE_MEDIA_EXTENSIONS:
            return False
        if kind is None:
            return True
        try:
            safe_kind = cls._safe_kind(kind)
        except ReferenceStaticStorageError:
            return False
        return normalized.startswith(f"{safe_kind}/")

    @classmethod
    def _extension(cls, *, filename: str, content_type: str) -> str:
        # ``filename`` is intentionally ignored: it is attacker-controlled and
        # must never decide how StaticFiles later classifies the response.
        del filename
        normalized = cls.normalize_content_type(content_type)
        extension = cls.SAFE_MEDIA_EXTENSIONS.get(normalized)
        if extension is None:
            raise ReferenceStaticStorageError("Unsupported reference media type")
        return extension

    @classmethod
    def persist_stream(
        cls,
        stream: BinaryIO,
        *,
        user_id: uuid.UUID,
        kind: str,
        file_hash: str,
        filename: str,
        content_type: str,
        expected_size: int | None = None,
    ) -> tuple[str, Path, int]:
        safe_kind = cls._safe_kind(kind)
        if not cls.supports_content_type(content_type, kind=safe_kind):
            raise ReferenceStaticStorageError("Reference media type does not match kind")
        digest = str(file_hash or "").strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ReferenceStaticStorageError("Reference hash must be SHA-256")

        now = datetime.now(UTC)
        relative_dir = Path(safe_kind) / str(user_id) / f"{now:%Y}" / f"{now:%m}"
        target_dir = cls.ensure_root() / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        extension = cls._extension(filename=filename, content_type=content_type)
        target = target_dir / f"{digest}{extension}"

        if target.is_file() and target.stat().st_size > 0:
            size = int(target.stat().st_size)
            if expected_size is not None and expected_size >= 0 and size != int(expected_size):
                raise ReferenceStaticStorageError("Stored reference size does not match upload")
            relative = target.relative_to(cls.root()).as_posix()
            return cls.public_url(relative), target, size

        original_position = stream.tell()
        stream.seek(0)
        temp_handle = tempfile.NamedTemporaryFile(
            prefix=".roxy-ref-",
            suffix=".part",
            dir=target_dir,
            delete=False,
        )
        temp_path = Path(temp_handle.name)
        computed = hashlib.sha256()
        size = 0
        try:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                computed.update(chunk)
                size += len(chunk)
                temp_handle.write(chunk)
            temp_handle.flush()
            os.fsync(temp_handle.fileno())
            temp_handle.close()

            if size <= 0:
                raise ReferenceStaticStorageError("Reference media is empty")
            if computed.hexdigest() != digest:
                raise ReferenceStaticStorageError("Reference upload hash mismatch")
            if expected_size is not None and expected_size >= 0 and size != int(expected_size):
                raise ReferenceStaticStorageError("Reference upload size mismatch")

            os.replace(temp_path, target)
            try:
                os.chmod(target, 0o644)
            except OSError:
                pass
        except Exception:
            try:
                temp_handle.close()
            except Exception:
                pass
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            stream.seek(original_position)

        relative = target.relative_to(cls.root()).as_posix()
        return cls.public_url(relative), target, size

    @classmethod
    def import_file(
        cls,
        source: Path,
        *,
        user_id: uuid.UUID,
        kind: str,
        filename: str,
        content_type: str,
    ) -> tuple[str, Path, int, str]:
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        file_hash = digest.hexdigest()
        with source.open("rb") as handle:
            url, target, size = cls.persist_stream(
                handle,
                user_id=user_id,
                kind=kind,
                file_hash=file_hash,
                filename=filename,
                content_type=content_type,
                expected_size=source.stat().st_size,
            )
        return url, target, size, file_hash

    @classmethod
    def remove_url(cls, value: str | None) -> None:
        if not value:
            return
        path = cls.path_for_url(value)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return

    @classmethod
    def copy_to_stream(cls, value: str, destination: BinaryIO) -> tuple[Path, int]:
        path = cls.path_for_url(value)
        if path is None or not path.is_file():
            raise ReferenceStaticStorageError("Stored reference media is missing")
        with path.open("rb") as source:
            shutil.copyfileobj(source, destination)
        return path, int(path.stat().st_size)
