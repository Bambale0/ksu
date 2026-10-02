from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.providers.neironych_errors import (
    NeironychProviderError,
    provider_error as _safe_error,
)

from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)

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
_TERMINAL_FAILURE = frozenset({"failed", "expired", "error", "cancelled", "canceled"})
_DOWNLOAD_RANGE_CHUNK_BYTES = 256 * 1024
_DOWNLOAD_ZERO_PROGRESS_LIMIT = 4
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$")


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
        storage_client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise NeironychProviderError("NEIRONYCH_API_KEY is not configured")
        self._authorization = f"Bearer {clean_key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=False,
        )
        self._storage_client = storage_client

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
        model: str,
        media_type: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        if model not in SEEDANCE_TEST_MODELS:
            raise NeironychProviderError(f"Unsupported admin-test model: {model}")
        kind = str(media_type or "").strip().lower()
        if kind not in {"image", "video", "audio"}:
            raise NeironychProviderError(f"Unsupported media type: {media_type}")
        if not content:
            raise NeironychProviderError("Cannot upload an empty media file")

        content_type = str(mime_type or "").strip().lower()
        if not content_type:
            raise NeironychProviderError("Media content type is required")
        expected_prefix = {
            "image": "image/",
            "video": "video/",
            "audio": "audio/",
        }[kind]
        if not content_type.startswith(expected_prefix):
            raise NeironychProviderError(
                f"Media content type {content_type!r} does not match type {kind!r}"
            )

        response = await self._client.post(
            "/v1/media/uploads",
            headers={
                **self._headers(),
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "type": kind,
                "content_type": content_type,
                "size_bytes": len(content),
            },
        )
        if not response.is_success:
            raise _safe_error(response)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise NeironychProviderError(
                "Neironych API returned malformed JSON for media upload ticket",
                status_code=response.status_code,
            ) from exc

        source = payload
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            source = payload["data"]
        upload_url = (
            str(source.get("upload_url") or "").strip()
            if isinstance(source, dict)
            else ""
        )
        media_url = (
            str(source.get("media_url") or "").strip()
            if isinstance(source, dict)
            else ""
        )
        try:
            upload_target = httpx.URL(upload_url)
            media_target = httpx.URL(media_url)
        except Exception as exc:
            raise NeironychProviderError("Neironych media upload ticket contains invalid URLs") from exc
        if (
            upload_target.scheme != "https"
            or not upload_target.host
            or media_target.scheme != "https"
            or not media_target.host
        ):
            raise NeironychProviderError(
                "Neironych media upload ticket must contain HTTPS upload_url and media_url"
            )

        # The storage URL is pre-signed. Never forward the Neironych Bearer
        # token (or any Telegram token-bearing URL) to the storage host.
        if self._storage_client is not None:
            uploaded = await self._storage_client.put(
                upload_target,
                content=content,
                headers={"Content-Type": content_type},
            )
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
                follow_redirects=False,
            ) as storage_client:
                uploaded = await storage_client.put(
                    upload_target,
                    content=content,
                    headers={"Content-Type": content_type},
                )
        if not uploaded.is_success:
            raise NeironychProviderError(
                f"Media storage upload HTTP {uploaded.status_code}",
                status_code=uploaded.status_code,
            )
        return str(media_target)

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

        try:
            request_payload = normalize_neironych_video_input(model, payload)
        except NeironychVideoContractError as exc:
            raise NeironychProviderError(str(exc), status_code=422) from exc
        # Identity is selected in trusted admin UI / runtime model resolution.
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
        if not value:
            raise NeironychProviderError("request_id is required")
        if max_bytes <= 0:
            raise NeironychProviderError("max_bytes must be positive")

        headers = {
            "Authorization": self._authorization,
            "Accept": "video/mp4,application/octet-stream",
        }
        path.unlink(missing_ok=True)
        offset = 0
        total_size: int | None = None
        content_type = "video/mp4"
        zero_progress_failures = 0

        while total_size is None or offset < total_size:
            upper_bound = min(
                max_bytes - 1,
                offset + _DOWNLOAD_RANGE_CHUNK_BYTES - 1,
                (total_size - 1) if total_size is not None else max_bytes - 1,
            )
            request_headers = {
                **headers,
                "Range": f"bytes={offset}-{upper_bound}",
            }
            before = offset

            try:
                async with self._client.stream(
                    "GET",
                    f"/v1/videos/{value}/content",
                    headers=request_headers,
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

                    content_type = str(
                        response.headers.get("content-type") or content_type
                    ).split(";", 1)[0]

                    if response.status_code == 206:
                        raw_range = str(
                            response.headers.get("content-range") or ""
                        ).strip()
                        match = _CONTENT_RANGE_RE.fullmatch(raw_range)
                        if match is None:
                            raise NeironychProviderError(
                                "Neironych resumable download returned invalid Content-Range"
                            )
                        start = int(match.group(1))
                        end = int(match.group(2))
                        if start != offset or end < start:
                            raise NeironychProviderError(
                                "Neironych resumable download returned unexpected byte range"
                            )
                        raw_total = match.group(3)
                        if raw_total != "*":
                            advertised_total = int(raw_total)
                            if advertised_total > max_bytes:
                                raise NeironychProviderError(
                                    "Neironych video exceeds admin-test limit "
                                    f"of {max_bytes} bytes"
                                )
                            if total_size is not None and total_size != advertised_total:
                                raise NeironychProviderError(
                                    "Neironych content length changed during resume"
                                )
                            total_size = advertised_total
                    elif offset > 0:
                        raise NeironychProviderError(
                            "Neironych content endpoint ignored Range during resume"
                        )
                    else:
                        raw_length = str(
                            response.headers.get("content-length") or ""
                        ).strip()
                        if raw_length.isdigit():
                            advertised_total = int(raw_length)
                            if advertised_total > max_bytes:
                                raise NeironychProviderError(
                                    "Neironych video exceeds admin-test limit "
                                    f"of {max_bytes} bytes"
                                )
                            total_size = advertised_total

                    mode = "ab" if offset else "wb"
                    with path.open(mode) as handle:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            offset += len(chunk)
                            if offset > max_bytes:
                                raise NeironychProviderError(
                                    "Neironych video exceeds admin-test limit "
                                    f"of {max_bytes} bytes"
                                )
                            handle.write(chunk)

                    if response.status_code == 200 and total_size is None:
                        total_size = offset
            except httpx.TransportError as exc:
                if offset > before:
                    zero_progress_failures = 0
                    logger.warning(
                        "neironych_content_resume",
                        extra={
                            "request_id": value,
                            "offset": offset,
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue
                zero_progress_failures += 1
                if zero_progress_failures >= _DOWNLOAD_ZERO_PROGRESS_LIMIT:
                    raise NeironychProviderError(
                        "Neironych content download stalled without byte progress"
                    ) from exc
                logger.warning(
                    "neironych_content_retry_no_progress",
                    extra={
                        "request_id": value,
                        "offset": offset,
                        "attempt": zero_progress_failures,
                        "error_type": type(exc).__name__,
                    },
                )
                continue

            if offset > before:
                zero_progress_failures = 0
            else:
                zero_progress_failures += 1
                if zero_progress_failures >= _DOWNLOAD_ZERO_PROGRESS_LIMIT:
                    raise NeironychProviderError(
                        "Neironych content download returned no byte progress"
                    )

        if offset <= 0:
            raise NeironychProviderError("Neironych API returned empty video content")
        if total_size is not None and offset != total_size:
            raise NeironychProviderError(
                f"Neironych content size mismatch: received {offset}, expected {total_size}"
            )
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


def enabled_seedance_test_models(available: list[str]) -> tuple[str, ...]:
    if not available:
        return ()
    return tuple(
        model_name
        for model_name in SEEDANCE_TEST_MODELS
        if resolve_seedance_model(model_name, available) is not None
    )


def is_success_status(status: str) -> bool:
    return str(status or "").lower() in _TERMINAL_SUCCESS


def is_failure_status(status: str) -> bool:
    return str(status or "").lower() in _TERMINAL_FAILURE
