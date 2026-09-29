from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEEDANCE_TEST_MODELS = ("seedance-2.0", "seedance-2.5")
_SEEDANCE_MODEL_ALIASES = {
    "seedance-2.0": (
        "seedance-2.0",
        "seedance-2",
        "bytedance/seedance-2.0",
        "bytedance/seedance-2",
    ),
    "seedance-2.5": (
        "seedance-2.5",
        "bytedance/seedance-2.5",
    ),
}
_SUPPORTED_PROVIDER_MODELS = frozenset(
    alias
    for aliases in _SEEDANCE_MODEL_ALIASES.values()
    for alias in aliases
)
_TERMINAL_SUCCESS = frozenset({"completed", "succeeded", "success", "done", "ready"})
_TERMINAL_FAILURE = frozenset({"failed", "error", "cancelled", "canceled"})


class NeironychProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


_LONG_TOKEN_RE = re.compile(r"(?i)\b[a-f0-9]{32,}\b")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


def _redact_error_text(value: str) -> str:
    value = _LONG_TOKEN_RE.sub("[REDACTED]", value)
    return _URL_QUERY_RE.sub(r"\1?[REDACTED]", value)


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
        message = (response.text or "").strip()
    if not message:
        message = f"HTTP {response.status_code}"
    # The provider may echo upload URLs/tokens in errors. Never persist an
    # unbounded upstream body in logs or the admin task row.
    return NeironychProviderError(
        f"Neironych API HTTP {response.status_code}: {_redact_error_text(message)[:800]}",
        status_code=response.status_code,
        payload=payload,
    )


def _request_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("request_id", "id", "video_id"):
            value = payload.get(key)
            if value:
                return str(value).strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("request_id", "id", "video_id"):
                value = data.get(key)
                if value:
                    return str(value).strip()
    return ""


def _status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return str(source.get("status") or source.get("state") or "").strip().lower()


def _failure_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    error = source.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or "").strip()
    return str(error or source.get("error_message") or source.get("message") or "").strip()


class NeironychVideoClient:
    """Admin-lab client for the documented asynchronous /v1/videos contract."""

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
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._authorization,
            "Accept": "application/json",
        }

    async def list_models(self) -> list[str]:
        response = await self._client.get("/v1/models", headers=self._headers())
        if not response.is_success:
            raise _safe_error(response)
        payload = response.json()
        items: Any = payload
        if isinstance(payload, dict):
            for key in ("data", "models", "items"):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
        result: list[str] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    value = item.strip()
                elif isinstance(item, dict):
                    value = str(
                        item.get("id")
                        or item.get("model")
                        or item.get("model_id")
                        or item.get("name")
                        or ""
                    ).strip()
                else:
                    value = ""
                if value and value not in result:
                    result.append(value)
        return result

    async def upload_media(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        if not content:
            raise NeironychProviderError("Cannot upload an empty media file")
        response = await self._client.post(
            "/v1/media/uploads",
            headers=self._headers(),
            files={"file": (filename or "media.bin", content, mime_type or "application/octet-stream")},
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for media upload",
                status_code=response.status_code,
            ) from exc
        url = ""
        if isinstance(payload, dict):
            url = str(payload.get("url") or payload.get("media_url") or "").strip()
            if not url and isinstance(payload.get("data"), dict):
                url = str(
                    payload["data"].get("url")
                    or payload["data"].get("media_url")
                    or ""
                ).strip()
        if not url:
            raise NeironychProviderError(
                f"Neironych API upload response has no media URL: {str(payload)[:800]}"
            )
        return url

    async def create_video(
        self,
        *,
        model: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str:
        if model not in _SUPPORTED_PROVIDER_MODELS:
            raise NeironychProviderError(f"Unsupported admin-test model: {model}")
        idem = str(idempotency_key or "").strip()
        if len(idem) < 8 or len(idem) > 160:
            raise NeironychProviderError("Idempotency-Key must contain 8..160 characters")

        request_payload = dict(payload)
        # Identity is selected in trusted admin UI and cannot be overridden by
        # raw JSON. Everything else is intentionally passed through so the lab
        # follows provider additions without an app release.
        request_payload["model"] = model
        response = await self._client.post(
            "/v1/videos/generations",
            headers={
                **self._headers(),
                "Content-Type": "application/json",
                "Idempotency-Key": idem,
            },
            json=request_payload,
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for video creation",
                status_code=response.status_code,
            ) from exc
        request_id = _request_id(data)
        if not request_id:
            raise NeironychProviderError(
                f"Neironych API create response has no request_id: {str(data)[:800]}"
            )
        return request_id

    async def get_video(self, request_id: str) -> tuple[str, str, dict[str, Any]]:
        value = str(request_id or "").strip()
        if not value:
            raise NeironychProviderError("request_id is required")
        response = await self._client.get(
            f"/v1/videos/{value}",
            headers=self._headers(),
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for video status",
                status_code=response.status_code,
            ) from exc
        status = _status(payload)
        return status, _failure_message(payload), payload

    async def download_content_to(
        self,
        request_id: str,
        path: Path,
        *,
        max_bytes: int,
    ) -> str:
        value = str(request_id or "").strip()
        total = 0
        headers = {
            "Authorization": self._authorization,
            "Accept": "video/mp4,application/octet-stream",
        }
        async with self._client.stream(
            "GET",
            f"/v1/videos/{value}/content",
            headers=headers,
        ) as response:
            if not response.is_success:
                body = await response.aread()
                request = response.request
                buffered = httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    content=body,
                    request=request,
                )
                raise _safe_error(buffered)
            content_type = str(response.headers.get("content-type") or "video/mp4").split(";", 1)[0]
            with path.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise NeironychProviderError(
                            f"Neironych video exceeds admin-test limit of {max_bytes} bytes"
                        )
                    handle.write(chunk)
        if total <= 0:
            raise NeironychProviderError("Neironych API returned empty video content")
        return content_type or "video/mp4"


def resolve_seedance_model(requested: str, available: list[str]) -> str | None:
    if not available:
        return requested if requested in SEEDANCE_TEST_MODELS else None
    aliases = _SEEDANCE_MODEL_ALIASES.get(requested, (requested,))
    exact = {item.strip(): item.strip() for item in available if item.strip()}
    for candidate in aliases:
        if candidate in exact:
            return exact[candidate]
    return None


def is_success_status(status: str) -> bool:
    return str(status or "").lower() in _TERMINAL_SUCCESS


def is_failure_status(status: str) -> bool:
    return str(status or "").lower() in _TERMINAL_FAILURE
