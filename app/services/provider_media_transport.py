from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.providers.kie import KieProviderError
from app.providers.kie_uploads import KieUploadClient
from app.services.feed_static import FeedStaticStorage
from app.services.reference_static import ReferenceStaticStorage


class ProviderMediaTransportError(RuntimeError):
    """Safe-to-retry failure before a generation task can exist upstream."""


class ProviderMediaTransportPermanentError(ProviderMediaTransportError):
    """Local/configuration failure that retrying cannot repair by itself."""


class ProviderMediaTransport:
    """Resolve product-owned media into fresh provider URLs for one submission.

    Generation drafts and reference memory keep stable ROXY URLs. Kie upload URLs
    are deliberately short-lived transport details and are never written back to
    generation parameters or the user's reference library.

    Like ``banano_kling:tanyapi``, local images that providers commonly reject
    (WEBP/GIF/etc.) are normalized to a cached PNG transport artifact. The saved
    reference itself remains untouched and keeps its original stable ROXY URL.

    API and worker processes are allowed to have separate local filesystems. If a
    stable ROXY URL resolves to a missing local file in the worker, the worker
    re-fetches that exact product-owned path from PUBLIC_BASE_URL and then uploads
    the recovered bytes to Kie. The recovery URL is always rebuilt from trusted
    configuration; user-controlled hosts and redirects are never followed.
    """

    @staticmethod
    def _local_path(value: str) -> Path | None:
        path = ReferenceStaticStorage.path_for_url(value)
        if path is not None:
            return path
        return FeedStaticStorage.path_for_url(value)

    @classmethod
    def _contains_local_media(cls, value: Any) -> bool:
        if isinstance(value, str):
            return cls._local_path(value) is not None
        if isinstance(value, (list, tuple)):
            return any(cls._contains_local_media(item) for item in value)
        if isinstance(value, dict):
            return any(cls._contains_local_media(item) for item in value.values())
        return False

    @staticmethod
    def _content_type(path: Path) -> str:
        guessed, _encoding = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _canonical_owned_url(cls, value: str) -> str | None:
        if cls._local_path(value) is None:
            return None
        base = urlsplit(settings.public_base_url.strip())
        if base.scheme != "https" or not base.netloc:
            return None
        source = urlsplit(value)
        path = source.path or (value if value.startswith("/") else "")
        if not path.startswith("/"):
            return None
        return urlunsplit((base.scheme, base.netloc, path, "", ""))

    @staticmethod
    def _recovery_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(connect=8.0, read=120.0, write=10.0, pool=8.0),
        )

    @classmethod
    async def _recover_owned_media(cls, value: str, expected_path: Path) -> Path:
        recovery_url = cls._canonical_owned_url(value)
        if recovery_url is None:
            raise ProviderMediaTransportPermanentError(
                "Stored provider input is unavailable on this worker"
            )

        suffix = expected_path.suffix[:16] if expected_path.suffix else ".bin"
        handle = tempfile.NamedTemporaryFile(
            prefix=".roxy-provider-recovery-",
            suffix=suffix,
            delete=False,
        )
        temp_path = Path(handle.name)
        handle.close()
        total = 0
        try:
            async with cls._recovery_client() as client:
                async with client.stream("GET", recovery_url, headers={"Accept": "*/*"}) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError:
                            declared_size = 0
                        if declared_size > settings.kie_upload_max_bytes:
                            raise ProviderMediaTransportPermanentError(
                                "Stored provider input exceeds the provider upload limit"
                            )
                    with temp_path.open("wb") as output:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > settings.kie_upload_max_bytes:
                                raise ProviderMediaTransportPermanentError(
                                    "Stored provider input exceeds the provider upload limit"
                                )
                            output.write(chunk)
            if total <= 0:
                raise ProviderMediaTransportPermanentError(
                    "Stored provider input is empty"
                )
            return temp_path
        except ProviderMediaTransportPermanentError:
            temp_path.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            temp_path.unlink(missing_ok=True)
            raise ProviderMediaTransportError(
                "Stored provider input could not be recovered from ROXY storage"
            ) from exc

    @classmethod
    def _normalize_image_sync(cls, path: Path) -> Path:
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png"}:
            return path
        guessed = cls._content_type(path)
        if not guessed.startswith("image/"):
            return path

        digest = cls._sha256(path)
        cache_root = ReferenceStaticStorage.ensure_root() / ".provider"
        cache_root.mkdir(parents=True, exist_ok=True)
        target = cache_root / f"{digest}.png"
        if target.is_file() and target.stat().st_size > 0:
            return target

        temp_handle = tempfile.NamedTemporaryFile(
            prefix=".roxy-provider-image-",
            suffix=".png",
            dir=cache_root,
            delete=False,
        )
        temp_path = Path(temp_handle.name)
        temp_handle.close()
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened)
                image.seek(0)
                image.load()
                if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                    converted = image.convert("RGBA" if "transparency" in image.info else "RGB")
                    if image is not opened:
                        image.close()
                    image = converted
                image.save(temp_path, format="PNG", optimize=True)
                if image is not opened:
                    image.close()
            os.replace(temp_path, target)
            try:
                os.chmod(target, 0o644)
            except OSError:
                pass
            return target
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            temp_path.unlink(missing_ok=True)
            raise ProviderMediaTransportPermanentError(
                f"Stored image cannot be normalized for provider transport: {path.name}"
            ) from exc

    @classmethod
    async def _provider_safe_path(cls, path: Path) -> Path:
        return await asyncio.to_thread(cls._normalize_image_sync, path)

    @classmethod
    async def prepare(cls, payload: dict[str, Any]) -> dict[str, Any]:
        if not cls._contains_local_media(payload):
            return payload
        if not settings.kie_api_key.strip():
            raise ProviderMediaTransportPermanentError(
                "KIE_API_KEY is required to transport stored reference media"
            )

        cache: dict[str, str] = {}
        client = KieUploadClient(settings.kie_api_key, settings.kie_upload_base_url)
        try:
            async def resolve(value: Any) -> Any:
                if isinstance(value, str):
                    path = cls._local_path(value)
                    if path is None:
                        return value
                    cached = cache.get(value)
                    if cached:
                        return cached

                    recovered_path: Path | None = None
                    if not path.is_file() or path.stat().st_size <= 0:
                        recovered_path = await cls._recover_owned_media(value, path)
                        path = recovered_path
                    try:
                        provider_path = await cls._provider_safe_path(path)
                        try:
                            with provider_path.open("rb") as stream:
                                uploaded = await client.upload_stream(
                                    file_name=provider_path.name,
                                    content_type=cls._content_type(provider_path),
                                    stream=stream,
                                    upload_path="ksu/runtime-inputs",
                                )
                        except KieProviderError as exc:
                            raise ProviderMediaTransportError(
                                f"Provider media upload failed: {exc}"
                            ) from exc
                    finally:
                        if recovered_path is not None:
                            recovered_path.unlink(missing_ok=True)
                    cache[value] = uploaded.url
                    return uploaded.url
                if isinstance(value, list):
                    return [await resolve(item) for item in value]
                if isinstance(value, tuple):
                    return [await resolve(item) for item in value]
                if isinstance(value, dict):
                    return {key: await resolve(item) for key, item in value.items()}
                return value

            prepared = await resolve(payload)
            if not isinstance(prepared, dict):
                raise ProviderMediaTransportPermanentError(
                    "Provider payload must remain an object"
                )
            return prepared
        finally:
            await client.aclose()
