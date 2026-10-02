from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

_LONG_TOKEN_RE = re.compile(r"(?i)\b[a-f0-9]{32,}\b")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,95}$")
KNOWN_CODES = frozenset({
    "api_key_required", "invalid_api_key", "insufficient_balance", "partner_not_active",
    "model_not_available", "generation_not_found", "content_not_available",
    "idempotency_conflict", "request_already_submitted", "capability_mismatch",
    "media_asset_not_ready", "invalid_request_contract", "invalid_idempotency_key",
    "invalid_previous_response", "unknown_model_contract", "upload_rejected",
    "provider_rejected_request", "provider_rate_limited", "provider_temporarily_unavailable",
    "upload_unavailable", "submission_outcome_unknown", "provider_response_invalid",
    "unexpected_provider_stream", "media_upload_requires_json", "multipart_not_supported_for_protocol",
})


def redact_error_text(value: str) -> str:
    return _URL_QUERY_RE.sub(r"\1?[REDACTED]", _LONG_TOKEN_RE.sub("[REDACTED]", value))


def request_identifier(value: Any) -> str | None:
    return value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else None


def extract_error_code(payload: Any, message: str = "") -> str | None:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            for name in ("code", "type", "message"):
                raw = error.get(name)
                if isinstance(raw, str) and _CODE.fullmatch(raw):
                    return raw
        detail = payload.get("detail")
        if isinstance(detail, str) and _CODE.fullmatch(detail):
            return detail
    # Compatibility for exceptions constructed by older callers/tests. Only
    # recognized contract identifiers are inferred from a free-form message.
    return next((code for code in sorted(KNOWN_CODES) if code in message.split()), None)


def retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.strip()
    if raw.isdecimal():
        return int(raw) if len(raw) < 10 else None
    try:
        at = parsedate_to_datetime(raw)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return max(0, math.ceil((at - datetime.now(UTC)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


class NeironychProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None,
                 payload: Any = None, request_id: str | None = None,
                 error_code: str | None = None, retry_after: int | None = None,
                 local_validation: bool = False) -> None:
        super().__init__(redact_error_text(message)[:1000])
        self.status_code = status_code
        self.payload = payload
        self.request_id = request_identifier(request_id)
        self.error_code = error_code or extract_error_code(payload, message)
        self.retry_after = retry_after
        self.local_validation = local_validation


def provider_error(response: httpx.Response) -> NeironychProviderError:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("detail") or error.get("type") or error.get("code") or "")
        if not message:
            detail = payload.get("detail")
            # Pydantic validation errors may echo a private input: never include
            # the full detail list, 'input' or 'ctx' in an exception/log.
            message = "invalid_request_contract" if isinstance(detail, list) else str(detail or payload.get("message") or "")
    code = extract_error_code(payload, message)
    request_id = request_identifier(response.headers.get("X-Request-Id"))
    if request_id is None and isinstance(payload, dict):
        request_id = request_identifier(payload.get("request_id"))
    return NeironychProviderError(
        f"Neironych API HTTP {response.status_code}: {message or code or 'provider_error'}",
        status_code=response.status_code, payload=payload, request_id=request_id,
        error_code=code, retry_after=retry_after_seconds(response.headers.get("Retry-After")),
    )
