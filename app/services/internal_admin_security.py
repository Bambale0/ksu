from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class InternalAdminSignature:
    request_id: str
    timestamp: int
    raw_body: bytes


def signature_payload(
    *,
    timestamp: int,
    request_id: str,
    method: str,
    path: str,
    raw_body: bytes,
) -> bytes:
    prefix = f"{timestamp}\n{request_id}\n{method.upper()}\n{path}\n".encode("utf-8")
    return prefix + raw_body


def calculate_signature(
    secret: str,
    *,
    timestamp: int,
    request_id: str,
    method: str,
    path: str,
    raw_body: bytes,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        signature_payload(
            timestamp=timestamp,
            request_id=request_id,
            method=method,
            path=path,
            raw_body=raw_body,
        ),
        hashlib.sha256,
    ).hexdigest()


def _parse_networks(value: str) -> tuple[ipaddress._BaseNetwork, ...]:  # type: ignore[name-defined]
    networks = []
    for item in value.split(","):
        raw = item.strip()
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError as exc:
            raise RuntimeError(f"Invalid INTERNAL_ADMIN_NETWORK_ALLOWLIST entry: {raw}") from exc
    return tuple(networks)


def ip_allowed(host: str | None, allowlist: str) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    networks = _parse_networks(allowlist)
    return bool(networks) and any(address in network for network in networks)


def verify_timestamp(timestamp: int, *, now: int | None = None, skew_seconds: int | None = None) -> bool:
    current = int(time.time() if now is None else now)
    skew = settings.internal_admin_timestamp_skew_seconds if skew_seconds is None else skew_seconds
    return abs(current - timestamp) <= max(0, int(skew))


async def verify_internal_admin_request(request: Request) -> InternalAdminSignature:
    secret = settings.internal_admin_hmac_secret.strip()
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal admin API is not configured",
        )

    host = request.client.host if request.client else None
    try:
        allowed = ip_allowed(host, settings.internal_admin_network_allowlist)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal admin network policy is invalid",
        ) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Network not allowed")

    timestamp_raw = request.headers.get("X-Admin-Timestamp", "")
    request_id = request.headers.get("X-Request-Id", "").strip()
    supplied = request.headers.get("X-Admin-Signature", "").strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied.split("=", 1)[1]
    if not timestamp_raw or not request_id or not supplied:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin signature headers")
    if len(request_id) > 96:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request id")
    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin timestamp") from exc
    if not verify_timestamp(timestamp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin signature expired")

    raw_body = await request.body()
    expected = calculate_signature(
        secret,
        timestamp=timestamp,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        raw_body=raw_body,
    )
    if not hmac.compare_digest(expected, supplied.lower()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin signature")

    request.state.request_id = request_id
    return InternalAdminSignature(request_id=request_id, timestamp=timestamp, raw_body=raw_body)
