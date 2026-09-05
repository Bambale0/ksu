from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

LOCAL_MEDIA_BUCKET = "__ksu_server_local__"
_DEFAULT_MEDIA_ROOT = "static/uploads/media"


class LocalMediaStorageError(RuntimeError):
    pass


class LocalMediaStorage:
    """Private durable generation-media storage on the KSU host.

    Files live below ``static/uploads/media`` by default, which is covered by the
    existing ``./static/uploads:/app/static/uploads`` Docker bind mount. The root
    is deliberately not mounted with FastAPI ``StaticFiles``: access to generated
    media continues to go through the owner/publication-scoped media API.
    """

    @classmethod
    def root(cls) -> Path:
        configured = os.environ.get("MEDIA_LOCAL_ROOT", _DEFAULT_MEDIA_ROOT).strip()
        root = Path(configured or _DEFAULT_MEDIA_ROOT).expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        return root.resolve()

    @classmethod
    def ensure_root(cls) -> Path:
        root = cls.root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def is_local_bucket(bucket: str | None) -> bool:
        return str(bucket or "") == LOCAL_MEDIA_BUCKET

    @classmethod
    def path_for_key(cls, key: str) -> Path:
        clean_key = str(key or "").strip().replace("\\", "/")
        if not clean_key or clean_key.startswith("/"):
            raise LocalMediaStorageError("Invalid local media object key")
        root = cls.ensure_root()
        target = (root / clean_key).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise LocalMediaStorageError("Local media object key escapes storage root") from exc
        return target

    @classmethod
    def persist_file(cls, source: Path, *, key: str) -> Path:
        if not source.is_file():
            raise LocalMediaStorageError("Downloaded media file does not exist")
        target = cls.path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.chmod(temporary, 0o640)
            os.replace(temporary, target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise LocalMediaStorageError(f"Unable to persist media on server: {exc}") from exc
        return target
