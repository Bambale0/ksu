from __future__ import annotations

import re
from dataclasses import dataclass
from typing import BinaryIO, Any

import httpx

from app.providers.kie import KieProviderError


@dataclass(slots=True)
class KieUploadedFile:
    url: str
    name: str
    mime_type: str
    size: int | None
    raw: dict[str, Any]


def safe_file_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return (cleaned or "upload")[:160]


class KieUploadClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://kieai.redpandaai.co",
    ) -> None:
        if not api_key:
            raise KieProviderError("KIE_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def upload_stream(
        self,
        *,
        file_name: str,
        content_type: str,
        stream: BinaryIO,
        upload_path: str = "ksu/user-uploads",
    ) -> KieUploadedFile:
        response = await self._client.post(
            "/api/file-stream-upload",
            data={"uploadPath": upload_path, "fileName": safe_file_name(file_name)},
            files={"file": (safe_file_name(file_name), stream, content_type)},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is False:
            raise KieProviderError(f"Kie upload failed: {payload!r}")
        data = payload.get("data") or {}
        url = data.get("fileUrl") or data.get("downloadUrl")
        if not url:
            raise KieProviderError(f"Kie upload returned no URL: {payload!r}")
        size_raw = data.get("fileSize")
        size = int(size_raw) if isinstance(size_raw, (int, float, str)) and str(size_raw).isdigit() else None
        return KieUploadedFile(
            url=str(url),
            name=str(data.get("fileName") or file_name),
            mime_type=str(data.get("mimeType") or content_type),
            size=size,
            raw=payload,
        )
