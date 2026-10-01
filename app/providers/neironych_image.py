from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.providers.neironych_video import NeironychProviderError


_LONG_TOKEN_RE = re.compile(r"(?i)\b[a-f0-9]{32,}\b")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


def _redact_error_text(value: str) -> str:
    value = _LONG_TOKEN_RE.sub("[REDACTED]", value)
    return _URL_QUERY_RE.sub(r"\1?[REDACTED]", value)


@dataclass(frozen=True, slots=True)
class NeironychImageResult:
    content: bytes
    content_type: str = "image/jpeg"


class NeironychImageClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise NeironychProviderError("NEIRONYCH_API_KEY is not configured")
        self._authorization = f"Bearer {clean_key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(180.0, connect=10.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            "Authorization": self._authorization,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }

    @staticmethod
    def _validate(
        *,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        image_urls: list[str],
        idempotency_key: str,
    ) -> None:
        if not str(prompt or "").strip():
            raise NeironychProviderError("Prompt must not be empty", status_code=422)
        if len(str(idempotency_key or "")) < 8 or len(str(idempotency_key or "")) > 160:
            raise NeironychProviderError("Idempotency-Key must contain 8..160 characters", status_code=422)
        if str(resolution or "").lower() not in {"1k", "2k", "4k"}:
            raise NeironychProviderError("Nano Banana Pro resolution must be 1K, 2K or 4K", status_code=422)
        if not str(aspect_ratio or "").strip():
            raise NeironychProviderError("Nano Banana Pro aspect_ratio is required", status_code=422)
        if len(image_urls) > 14:
            raise NeironychProviderError("Nano Banana Pro accepts at most 14 reference images", status_code=422)
        for url in image_urls:
            if not str(url).startswith("https://"):
                raise NeironychProviderError("Nano Banana Pro references must be public HTTPS URLs", status_code=422)

    @staticmethod
    def _safe_error(response: httpx.Response) -> NeironychProviderError:
        try:
            payload: Any = response.json()
        except Exception:
            payload = None
        message = ""
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or error.get("detail") or "").strip()
            if not message:
                message = str(payload.get("message") or payload.get("detail") or "").strip()
        if not message:
            message = f"HTTP {response.status_code}"
        return NeironychProviderError(
            f"Neironych API HTTP {response.status_code}: {_redact_error_text(message)[:600]}",
            status_code=response.status_code,
            payload=payload,
        )

    async def create_nano_banana_pro(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        image_urls: list[str],
        idempotency_key: str,
    ) -> NeironychImageResult:
        refs = list(dict.fromkeys(str(item).strip() for item in image_urls if str(item).strip()))
        self._validate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            image_urls=refs,
            idempotency_key=idempotency_key,
        )
        payload: dict[str, Any] = {
            "model": "nano-banana-pro",
            "prompt": str(prompt).strip(),
            "n": 1,
            "resolution": str(resolution).lower(),
            "aspect_ratio": str(aspect_ratio).strip(),
            "response_format": "b64_json",
        }
        path = "/v1/images/generations"
        if refs:
            path = "/v1/images/edits"
            payload["images"] = [{"image_url": url} for url in refs]

        response = await self._client.post(
            path,
            headers=self._headers(idempotency_key),
            json=payload,
        )
        if not response.is_success:
            raise self._safe_error(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for image generation",
                status_code=response.status_code,
            ) from exc
        rows = data.get("data") if isinstance(data, dict) else None
        first = rows[0] if isinstance(rows, list) and rows else None
        encoded = first.get("b64_json") if isinstance(first, dict) else None
        if not encoded:
            raise NeironychProviderError("Neironych image response has no data[0].b64_json")
        try:
            content = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise NeironychProviderError("Neironych image response contains invalid base64") from exc
        if not content:
            raise NeironychProviderError("Neironych image response decoded to empty content")
        return NeironychImageResult(content=content)
