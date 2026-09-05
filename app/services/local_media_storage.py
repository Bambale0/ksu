from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import time
import uuid
from pathlib import Path

from app.core.config import settings

LOCAL_MEDIA_BUCKET = "__ksu_server_local__"
_DEFAULT_MEDIA_ROOT = "static/uploads/media"
_SIGNING_CONTEXT = b"ksu-local-media-url-v1"


class LocalMediaStorageError(RuntimeError):
    pass


class LocalMediaStorage:
    """Private durable generation-media storage on the KSU host.

    Files live below ``static/uploads/media`` by default, which is covered by the
    existing ``./static/uploads:/app/static/uploads`` Docker bind mount. The root
    is deliberately not mounted with FastAPI ``StaticFiles``: access to generated
    media continues to go through publication checks or short-lived signed URLs.
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

    @staticmethod
    def _signing_key() -> bytes:
        # Production deploy guarantees a persistent ADMIN_SECURITY_KEY. Derive a
        # domain-separated media key instead of introducing another operator secret.
        raw = str(settings.admin_security_key or settings.telegram_webhook_secret or "").strip()
        if not raw:
            if settings.is_production:
                raise LocalMediaStorageError("Private media signing key is not configured")
            raw = "ksu-development-local-media-key"
        return hmac.new(raw.encode("utf-8"), _SIGNING_CONTEXT, hashlib.sha256).digest()

    @classmethod
    def _signature(cls, *, asset_id: str, key: str, expires: int) -> str:
        payload = f"{asset_id}\n{key}\n{expires}".encode("utf-8")
        return hmac.new(cls._signing_key(), payload, hashlib.sha256).hexdigest()

    @classmethod
    def signed_view_url(
        cls,
        *,
        asset_id: uuid.UUID | str,
        key: str,
        ttl_seconds: int | None = None,
    ) -> str:
        asset_value = str(asset_id)
        expires = int(time.time()) + max(60, int(ttl_seconds or settings.media_presign_ttl_seconds))
        signature = cls._signature(asset_id=asset_value, key=key, expires=expires)
        return f"/api/v1/media/{asset_value}/signed/{expires}/{signature}"

    @classmethod
    def verify_view_signature(
        cls,
        *,
        asset_id: uuid.UUID | str,
        key: str,
        expires: int,
        signature: str,
    ) -> bool:
        if expires < int(time.time()):
            return False
        expected = cls._signature(asset_id=str(asset_id), key=key, expires=expires)
        return hmac.compare_digest(expected, str(signature or ""))
