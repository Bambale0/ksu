from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, BinaryIO

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


def _retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


class KieUploadClient:
    """Kie file-stream uploader hardened for Mini App reference uploads.

    The production `banano_kling:tanyapi` backend treats media upload as its own
    resilient boundary before generation. ROXY keeps its FastAPI/httpx stack but
    adopts the same boundary: provider transport errors never leak through the
    API, transient upstream failures are retried, and every retry rewinds the
    spooled upload stream before sending it again.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://kieai.redpandaai.co",
        *,
        max_attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise KieProviderError("KIE_API_KEY is not configured")
        self._max_attempts = max(1, int(max_attempts))
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _rewind(stream: BinaryIO) -> None:
        try:
            stream.seek(0)
        except (AttributeError, OSError) as exc:
            raise KieProviderError("Reference upload stream is not seekable") from exc

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise KieProviderError(
                f"Kie upload returned invalid JSON (HTTP {response.status_code})"
            ) from exc
        if not isinstance(payload, dict):
            raise KieProviderError("Kie upload returned an invalid response")
        return payload

    async def upload_stream(
        self,
        *,
        file_name: str,
        content_type: str,
        stream: BinaryIO,
        upload_path: str = "ksu/user-uploads",
    ) -> KieUploadedFile:
        safe_name = safe_file_name(file_name)
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            self._rewind(stream)
            try:
                response = await self._client.post(
                    "/api/file-stream-upload",
                    data={"uploadPath": upload_path, "fileName": safe_name},
                    files={"file": (safe_name, stream, content_type)},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                await asyncio.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))
                continue

            if _retryable_status(response.status_code) and attempt < self._max_attempts:
                last_error = KieProviderError(
                    f"Kie upload temporary HTTP {response.status_code}"
                )
                await response.aread()
                await asyncio.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))
                continue

            if response.is_error:
                body = (await response.aread())[:512].decode("utf-8", errors="replace")
                raise KieProviderError(
                    f"Kie upload HTTP {response.status_code}: {body or 'upstream rejected upload'}"
                )

            payload = self._payload(response)
            if payload.get("success") is False:
                raise KieProviderError(f"Kie upload failed: {payload!r}")
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                raise KieProviderError(f"Kie upload returned invalid data: {payload!r}")
            url = data.get("fileUrl") or data.get("downloadUrl")
            if not url:
                raise KieProviderError(f"Kie upload returned no URL: {payload!r}")
            size_raw = data.get("fileSize")
            size = (
                int(size_raw)
                if isinstance(size_raw, (int, float, str)) and str(size_raw).isdigit()
                else None
            )
            return KieUploadedFile(
                url=str(url),
                name=str(data.get("fileName") or file_name),
                mime_type=str(data.get("mimeType") or content_type),
                size=size,
                raw=payload,
            )

        raise KieProviderError("Kie upload is temporarily unavailable") from last_error
