from __future__ import annotations

import hashlib
import mimetypes
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
    """

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

    @staticmethod
    def _extension(*, filename: str, content_type: str) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix and 1 < len(suffix) <= 12 and suffix[1:].isalnum():
            return suffix
        guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
        if guessed == ".jpe":
            return ".jpg"
        return guessed or ".bin"

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
