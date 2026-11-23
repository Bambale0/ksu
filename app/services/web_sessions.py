"""First-party web sessions; no synthetic Telegram initData or JWT in browser storage."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from redis.asyncio import Redis

from app.core.config import settings

COOKIE = "roxy_web_session"
SESSION_TTL = 7 * 24 * 60 * 60
SESSION_PREFIX = "roxy:web-session:"


def token_key(token: str) -> str:
    return SESSION_PREFIX + hashlib.sha256(token.encode("ascii")).hexdigest()


def assert_first_party(request: Request) -> None:
    """Mutating browser-cookie actions must be initiated by this origin."""
    origin = request.headers.get("origin", "").strip()
    allowed = urlsplit(settings.public_base_url).netloc if settings.public_base_url else request.headers.get("host", "")
    parsed = urlsplit(origin)
    if not origin or not allowed or parsed.netloc.lower() != allowed.lower() or parsed.scheme not in {"https", "http"}:
        raise HTTPException(403, "Origin verification failed")
    if settings.is_production and parsed.scheme != "https":
        raise HTTPException(403, "HTTPS required")


def redis_from_request(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(503, "Authentication storage unavailable")
    return redis


async def current_web_user_id(request: Request) -> uuid.UUID | None:
    token = str(request.cookies.get(COOKIE) or "")
    if len(token) < 38 or len(token) > 256:
        return None
    try:
        raw = await redis_from_request(request).get(token_key(token))
        return uuid.UUID(str(raw)) if raw else None
    except HTTPException:
        raise
    except (ValueError, TypeError):
        return None
    except Exception as exc:
        raise HTTPException(503, "Authentication storage unavailable") from exc


async def issue_web_session(request: Request, response: Response, user_id: uuid.UUID) -> None:
    redis = redis_from_request(request)
    prior_token = str(request.cookies.get(COOKIE) or "")
    token = secrets.token_urlsafe(48)
    try:
        await redis.set(token_key(token), str(user_id), ex=SESSION_TTL)
        if prior_token and len(prior_token) >= 38:
            await redis.delete(token_key(prior_token))
    except Exception as exc:
        raise HTTPException(503, "Authentication storage unavailable") from exc
    response.set_cookie(
        COOKIE, token, httponly=True, secure=settings.is_production,
        samesite="lax", max_age=SESSION_TTL, path="/",
    )
    response.headers["Cache-Control"] = "no-store"


async def revoke_web_session(request: Request, response: Response) -> None:
    token = str(request.cookies.get(COOKIE) or "")
    if token and len(token) >= 38:
        try:
            await redis_from_request(request).delete(token_key(token))
        except Exception as exc:
            raise HTTPException(503, "Authentication storage unavailable") from exc
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=settings.is_production, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
