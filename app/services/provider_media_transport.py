from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.kie_uploads import KieUploadClient
from app.services.feed_static import FeedStaticStorage
from app.services.reference_static import ReferenceStaticStorage


class ProviderMediaTransportError(RuntimeError):
    pass


class ProviderMediaTransport:
    """Resolve product-owned media into fresh provider URLs for one submission.

    Generation drafts and reference memory keep stable ROXY URLs. Kie upload URLs
    are deliberately short-lived transport details and are never written back to
    generation parameters or the user's reference library.
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
        if isinstance(value, list | tuple):
            return any(cls._contains_local_media(item) for item in value)
        if isinstance(value, dict):
            return any(cls._contains_local_media(item) for item in value.values())
        return False

    @staticmethod
    def _content_type(path: Path) -> str:
        guessed, _encoding = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"

    @classmethod
    async def prepare(cls, payload: dict[str, Any]) -> dict[str, Any]:
        if not cls._contains_local_media(payload):
            return payload
        if not settings.kie_api_key.strip():
            raise ProviderMediaTransportError(
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
                    if not path.is_file() or path.stat().st_size <= 0:
                        raise ProviderMediaTransportError(
                            f"Stored provider input is missing: {value}"
                        )
                    with path.open("rb") as stream:
                        uploaded = await client.upload_stream(
                            file_name=path.name,
                            content_type=cls._content_type(path),
                            stream=stream,
                            upload_path="ksu/runtime-inputs",
                        )
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
                raise ProviderMediaTransportError("Provider payload must remain an object")
            return prepared
        finally:
            await client.aclose()
