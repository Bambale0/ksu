from __future__ import annotations

import base64
import json
import re
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
IMAGE_MODELS = frozenset({"nano-banana-pro", "nano-banana-2", "nano-banana-2-lite", "gpt-image-2"})
_NANO_ASPECT_RATIOS = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"})


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
            "X-Client-Request-Id": idempotency_key,
            "X-Submission-Receipt": "v1",
        }

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
        if request_body is not None:
            _, expected = prepare_image_payload(
                prompt=prompt, aspect_ratio=aspect_ratio, resolution=resolution,
                image_urls=image_urls, idempotency_key=idempotency_key,
            )
            if json.loads(request_body) != expected:
                raise NeironychProviderError("Saved image request identity changed", local_validation=True)
        return await self.create_image(
            model="nano-banana-pro", prompt=prompt, aspect_ratio=aspect_ratio,
            resolution=resolution, image_urls=image_urls, idempotency_key=idempotency_key,
            request_body=request_body,
        )

    async def create_image(
        self, *, model: str, prompt: str, aspect_ratio: str, resolution: str,
        image_urls: list[str], idempotency_key: str, request_body: str | None = None,
    ) -> NeironychImageResult:
        if request_body is None:
            path, payload = prepare_image_payload(
                model=model, prompt=prompt, aspect_ratio=aspect_ratio, resolution=resolution,
                image_urls=image_urls, idempotency_key=idempotency_key,
            )
        else:
            # The service verified the immutable snapshot; do not rebuild its
            # size/reference fields under a potentially newer normalizer.
            payload = json.loads(request_body)
            if model not in IMAGE_MODELS or not isinstance(payload, dict) or payload.get("model") != model:
                raise NeironychProviderError("Saved image request model changed", local_validation=True)
            if not 8 <= len(idempotency_key) <= 160:
                raise NeironychProviderError("Invalid Idempotency-Key", local_validation=True)
            path = "/v1/images/edits" if payload.get("images") else "/v1/images/generations"
        response = await self._client.post(
            path,
            headers=self._headers(idempotency_key),
            content=request_body.encode("utf-8") if request_body is not None else encode_body(payload).encode("utf-8"),
        )
        if not response.is_success:
            raise provider_error(
                response,
                client_request_id=idempotency_key,
                idempotency_key=idempotency_key,
            )
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
        if not encoded and isinstance(first, dict) and isinstance(first.get("url"), str):
            # Live GPT edits may return the documented URL form even when
            # b64_json was requested. Reuse bounded public-HTTPS ingestion;
            # its separate client never receives provider credentials.
            from app.services.media_assets import MediaIngestError, MediaIngestService, UnsafeMediaSource
            try:
                downloaded = await MediaIngestService._download(first["url"])
                try:
                    content = downloaded.path.read_bytes()
                finally:
                    downloaded.path.unlink(missing_ok=True)
            except (MediaIngestError, UnsafeMediaSource, httpx.HTTPError, OSError, ValueError) as exc:
                raise NeironychProviderError(
                    "Neironych image result could not be downloaded safely",
                    request_id=response.headers.get("X-Request-Id"),
                    error_code="provider_response_invalid",
                ) from exc
            if not content:
                raise NeironychProviderError("Empty image download", error_code="provider_response_invalid")
            return NeironychImageResult(content=content,
                content_type=downloaded.content_type,
                request_id=request_identifier(response.headers.get("X-Request-Id")))
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
                          model: str = "nano-banana-pro",
                          image_urls: list[str], idempotency_key: str) -> tuple[str, dict[str, Any]]:
    refs = list(dict.fromkeys(str(item).strip() for item in image_urls if str(item).strip()))
    if model not in IMAGE_MODELS:
        raise NeironychProviderError("Unsupported Neironych image model", local_validation=True)
    if not str(prompt or "").strip():
        raise NeironychProviderError("Prompt must not be empty", status_code=422, local_validation=True)
    if not 8 <= len(idempotency_key) <= 160:
        raise NeironychProviderError("Invalid Idempotency-Key", status_code=422, local_validation=True)
    ratio = str(aspect_ratio).strip()
    resolution = str(resolution).lower()
    maximum = 16 if model == "gpt-image-2" else 14 if model == "nano-banana-pro" else 3
    ratios = NANO_PRO_ASPECT_RATIOS if model == "nano-banana-pro" else _NANO_ASPECT_RATIOS
    if len(refs) > maximum:
        raise _unsupported(f"{model} accepts at most {maximum} references")
    # Validate every reference, including GPT references 15 and 16.
    for url in refs:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise NeironychProviderError("References must be public HTTPS URLs", status_code=422, local_validation=True)
    payload: dict[str, Any] = {"model": model, "prompt": str(prompt).strip(),
        "n": 1, "response_format": "b64_json"}
    if model == "gpt-image-2":
        payload["size"] = _gpt_size(ratio, resolution)
    else:
        if ratio not in ratios:
            raise _unsupported(f"{model} does not support the requested aspect ratio")
        if resolution not in ({"1k"} if model == "nano-banana-2-lite" else {"1k", "2k", "4k"}):
            raise _unsupported(f"{model} does not support the requested resolution")
        payload.update(resolution=resolution, aspect_ratio=ratio)
    if refs:
        payload["images"] = [{"image_url": url} for url in refs]
    return ("/v1/images/edits" if refs else "/v1/images/generations"), payload


def _unsupported(message: str) -> NeironychProviderError:
    return NeironychProviderError(message, status_code=409, error_code="capability_mismatch", local_validation=True)


def _gpt_size(ratio: str, resolution: str) -> str:
    if resolution not in {"", "1k", "2k", "4k"}:
        raise _unsupported("Unsupported GPT Image 2 resolution")
    if ratio == "auto":
        if resolution:
            raise _unsupported("GPT Image 2 cannot combine automatic ratio with an explicit resolution")
        return "auto"
    if not re.fullmatch(r"[1-9][0-9]?:[1-9][0-9]?", ratio):
        raise _unsupported("GPT Image 2 aspect ratio cannot be represented")
    width, height = (int(value) for value in ratio.split(":"))
    # The provider accepts positive WIDTHxHEIGHT. Preserve the selected size
    # class and composition instead of passing an unsupported resolution field.
    pixels = {"": 1024, "1k": 1024, "2k": 2048, "4k": 4096}[resolution]
    scale = pixels / max(width, height)
    return f"{round(width * scale)}x{round(height * scale)}"
