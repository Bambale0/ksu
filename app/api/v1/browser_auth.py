from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

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
