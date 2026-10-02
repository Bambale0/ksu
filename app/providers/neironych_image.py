from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.neironych_errors import (
    NeironychProviderError,
    provider_error,
    request_identifier,
)

from app.providers.neironych_submission import encode_body

NANO_PRO_ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9")


@dataclass(frozen=True, slots=True)
class NeironychImageResult:
    content: bytes
    content_type: str = "image/jpeg"
    request_id: str | None = None


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
            raise NeironychProviderError("NEIRONYCH_API_KEY is not configured", status_code=401, error_code="api_key_required", local_validation=True)
        self._authorization = f"Bearer {clean_key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(180.0, connect=10.0),
            follow_redirects=False,
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
            raise NeironychProviderError("Prompt must not be empty", status_code=422, local_validation=True)
        if len(str(idempotency_key or "")) < 8 or len(str(idempotency_key or "")) > 160:
            raise NeironychProviderError("Idempotency-Key must contain 8..160 characters", status_code=422, local_validation=True)
        if str(resolution or "").lower() not in {"1k", "2k", "4k"}:
            raise NeironychProviderError("Nano Banana Pro resolution must be 1K, 2K or 4K", status_code=422, local_validation=True)
        if str(aspect_ratio or "").strip() not in NANO_PRO_ASPECT_RATIOS:
            raise NeironychProviderError("Nano Banana Pro requires a documented fixed aspect_ratio", status_code=422, local_validation=True)
        if len(image_urls) > 14:
            raise NeironychProviderError("Nano Banana Pro accepts at most 14 reference images", status_code=422, local_validation=True)
        for url in image_urls:
            parsed = urlsplit(str(url))
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise NeironychProviderError("Nano Banana Pro references must be public HTTPS URLs", status_code=422, local_validation=True)

    async def create_nano_banana_pro(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        image_urls: list[str],
        idempotency_key: str,
        request_body: str | None = None,
    ) -> NeironychImageResult:
        path, payload = prepare_image_payload(
            prompt=prompt, aspect_ratio=aspect_ratio, resolution=resolution,
            image_urls=image_urls, idempotency_key=idempotency_key,
        )
        if request_body is not None:
            frozen = json.loads(request_body)
            if frozen != payload:
                raise NeironychProviderError("Saved image request identity changed", local_validation=True)
        response = await self._client.post(
            path,
            headers=self._headers(idempotency_key),
            content=request_body.encode("utf-8") if request_body is not None else encode_body(payload).encode("utf-8"),
        )
        if not response.is_success:
            raise provider_error(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for image generation",
                status_code=response.status_code,
                request_id=response.headers.get("X-Request-Id"),
                error_code="provider_response_invalid",
            ) from exc
        rows = data.get("data") if isinstance(data, dict) else None
        first = rows[0] if isinstance(rows, list) and rows else None
        encoded = first.get("b64_json") if isinstance(first, dict) else None
        if not encoded:
            raise NeironychProviderError("Neironych image response has no data[0].b64_json", request_id=response.headers.get("X-Request-Id"), error_code="provider_response_invalid")
        try:
            content = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise NeironychProviderError("Neironych image response contains invalid base64", request_id=response.headers.get("X-Request-Id"), error_code="provider_response_invalid") from exc
        if not content:
            raise NeironychProviderError("Neironych image response decoded to empty content", request_id=response.headers.get("X-Request-Id"), error_code="provider_response_invalid")
        return NeironychImageResult(content=content, request_id=request_identifier(response.headers.get("X-Request-Id")))


def prepare_image_payload(*, prompt: str, aspect_ratio: str, resolution: str,
                          image_urls: list[str], idempotency_key: str) -> tuple[str, dict[str, Any]]:
    refs = list(dict.fromkeys(str(item).strip() for item in image_urls if str(item).strip()))
    NeironychImageClient._validate(prompt=prompt, aspect_ratio=aspect_ratio,
        resolution=resolution, image_urls=refs, idempotency_key=idempotency_key)
    payload: dict[str, Any] = {"model": "nano-banana-pro", "prompt": str(prompt).strip(),
        "n": 1, "resolution": str(resolution).lower(), "aspect_ratio": str(aspect_ratio).strip(),
        "response_format": "b64_json"}
    if refs:
        payload["images"] = [{"image_url": url} for url in refs]
    return ("/v1/images/edits" if refs else "/v1/images/generations"), payload
