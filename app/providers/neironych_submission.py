from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

# Contract limit, not a business setting. Signed reference URLs are private.
MAX_VIDEO_JSON_BYTES = 1024 * 1024
SNAPSHOT_KEY = "_neironych_submission"


def encode_body(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(body.encode("utf-8")) >= MAX_VIDEO_JSON_BYTES:
        raise ValueError("Neironych request JSON must be smaller than 1 MiB")
    return body


def freeze_submission(
    *,
    model: str,
    payload: dict[str, Any],
    key: str,
    base_url: str,
    endpoint: str = "/v1/videos/generations",
) -> dict[str, Any]:
    origin = base_url.rstrip("/")
    url = urlsplit(origin)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Neironych base URL must be an unauthenticated HTTPS origin")
    if url.path or url.query or url.fragment:
        raise ValueError("Neironych base URL must not include a path or query")
    if not 8 <= len(key) <= 160:
        raise ValueError("Invalid Neironych idempotency key")
    if endpoint not in {"/v1/videos/generations", "/v1/images/generations", "/v1/images/edits"}:
        raise ValueError("Unsupported Neironych submission endpoint")
    body = encode_body({**payload, "model": model})
    return {
        "version": 1,
        "base_url": origin,
        "endpoint": endpoint,
        "method": "POST",
        "model": model,
        "idempotency_key": key,
        "body_json": body,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def saved_body(snapshot: Any, *, model: str, key: str, base_url: str) -> str:
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise ValueError("Missing or unsupported Neironych submission snapshot")
    if (
        snapshot.get("model") != model
        or snapshot.get("idempotency_key") != key
        or snapshot.get("base_url") != base_url.rstrip("/")
        or snapshot.get("method") != "POST"
    ):
        raise ValueError("Neironych submission identity changed; reconciliation required")
    body = snapshot.get("body_json")
    if not isinstance(body, str) or hashlib.sha256(
        body.encode("utf-8")
    ).hexdigest() != snapshot.get("sha256"):
        raise ValueError("Neironych submission snapshot integrity check failed")
    data = json.loads(body)
    if not isinstance(data, dict) or data.get("model") != model:
        raise ValueError("Neironych submission model identity changed")
    return body
