from __future__ import annotations

import json
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import RedisDep, SessionDep
from app.services import browser_approval as approval
from app.services.browser_approval_policy import configured_browser_approval
from app.core.config import settings
from app.core.telegram_browser_auth import (
    build_browser_init_data,
    verify_telegram_login_widget,
)

router = APIRouter(prefix="/browser-auth", tags=["browser-auth"])


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: str = Field(min_length=1, max_length=256)
    last_name: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=64)
    photo_url: str | None = Field(default=None, max_length=2048)
    auth_date: int
    hash: str = Field(min_length=1, max_length=256)


class BrowserAuthRequest(BaseModel):
    telegram_auth: TelegramLoginPayload


@router.get("/config")
async def browser_auth_config(response: Response) -> dict[str, object]:
    username = settings.bot_username.strip().lstrip("@")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram login is unavailable",
        )
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"ok": True, "bot_username": username}


@router.post("")
async def browser_auth(
    payload: BrowserAuthRequest,
    response: Response,
) -> dict[str, object]:
    if not settings.bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram login is unavailable",
        )

    try:
        user = verify_telegram_login_widget(
            payload.telegram_auth.model_dump(exclude_none=True),
            settings.bot_token,
        )
        init_data = build_browser_init_data(user, settings.bot_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Telegram login",
        ) from exc

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return {
        "ok": True,
        "init_data": init_data,
        "expires_in": 24 * 60 * 60,
    }


# Device approval uses the same signed browser credential as the existing
# Telegram widget, without accepting a Telegram identity from browser input.
class ApprovalStart(BaseModel):
    purpose: str = Field(default="studio", pattern="^(studio|payments)$")


def _approval_origin(request: Request) -> None:
    configured = urlsplit(settings.public_base_url)
    expected = f"{configured.scheme}://{configured.netloc}"
    if not configured.netloc or request.headers.get("origin") != expected:
        raise HTTPException(403, "Invalid origin")


def _approval_cookie(request: Request):
    return approval.split_cookie(request.cookies.get(approval.COOKIE, ""))


def _approval_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _approval_url(ticket: str) -> str:
    bot = settings.bot_username.strip().lstrip("@")
    if not bot or not settings.bot_token:
        raise HTTPException(503, "Telegram login unavailable")
    return f"https://t.me/{bot}?start=auth_{ticket}"


@router.post("/approval/start")
async def approval_start(payload: ApprovalStart, request: Request, response: Response, redis: RedisDep, session: SessionDep):
    _approval_origin(request)
    _approval_url("placeholder")
    policy = await configured_browser_approval(session)
    result = await approval.issue(redis, _approval_cookie(request), payload.purpose,
                                  request.client.host if request.client else "unknown", limits=policy.limits())
    if result is None:
        raise HTTPException(429, "Too many login requests")
    ticket, proof, code = result
    response.set_cookie(approval.COOKIE, ticket + "." + proof, max_age=approval.TTL,
                        secure=True, httponly=True, samesite="lax", path=approval.ROOT)
    _approval_no_store(response)
    return {"status": "pending", "url": _approval_url(ticket), "code": code,
            "expires_in": approval.TTL, "purpose": payload.purpose}


@router.get("/approval/status")
async def approval_status(request: Request, response: Response, redis: RedisDep):
    _approval_no_store(response)
    pair = _approval_cookie(request)
    if not pair:
        return {"status": "idle"}
    result = await approval.transition(redis, pair[0], "status", proof=pair[1])
    if result[0] in ("pending", "approved"):
        return {"status": result[0], "url": _approval_url(pair[0]), "code": result[1],
                "purpose": result[2], "expires_in": max(0, int(result[3]))}
    return {"status": result[0]}


@router.post("/approval/claim")
async def approval_claim(request: Request, response: Response, redis: RedisDep):
    _approval_origin(request)
    if not settings.bot_token:
        raise HTTPException(503, "Telegram login unavailable")
    pair = _approval_cookie(request)
    if not pair:
        raise HTTPException(401, "No login request")
    result = await approval.transition(redis, pair[0], "claim", proof=pair[1])
    if result[0] != "consumed" or len(result) != 3:
        raise HTTPException(409, "Login request unavailable")
    user = json.loads(result[1])
    init_data = build_browser_init_data(user, settings.bot_token)
    approval.audit(pair[0], "credential_issued", "success", int(user["id"]))
    response.delete_cookie(approval.COOKIE, path=approval.ROOT, secure=True,
                           httponly=True, samesite="lax")
    _approval_no_store(response)
    return {"ok": True, "init_data": init_data, "expires_in": 86400, "purpose": result[2]}


@router.post("/approval/cancel")
async def approval_cancel(request: Request, response: Response, redis: RedisDep):
    _approval_origin(request)
    pair = _approval_cookie(request)
    if pair:
        await approval.transition(redis, pair[0], "cancel", proof=pair[1])
    response.delete_cookie(approval.COOKIE, path=approval.ROOT, secure=True,
                           httponly=True, samesite="lax")
    _approval_no_store(response)
    return {"ok": True}
