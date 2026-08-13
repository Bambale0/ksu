from typing import Annotated

from aiogram.types import User as TelegramUser
from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.db.session import get_session
from app.services.onboarding import OnboardingService
from app.services.users import UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]


def _path_is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _onboarding_gate_applies(request: Request) -> bool:
    if not settings.onboarding_enabled:
        return False
    method = request.method.upper()
    if method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
        return False

    path = request.url.path.rstrip("/")
    safe_prefixes = (
        "/api/v1/onboarding",
        "/api/v1/me",
        "/api/v1/support",
        "/api/v1/notifications",
    )
    if any(_path_is_under(path, prefix) for prefix in safe_prefixes):
        return False

    # Recovery/reversal actions must stay possible after an onboarding version bump.
    if path.endswith("/cancel") or path.endswith("/history/restore"):
        return False
    return path.startswith("/api/v1/")


async def get_current_user(
    request: Request,
    session: SessionDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> User:
    if not settings.bot_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot is not configured")
    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram initData")
    try:
        init_data = safe_parse_webapp_init_data(settings.bot_token, x_telegram_init_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram initData"
        ) from exc
    if init_data.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram user missing")
    web_user = init_data.user
    tg_user = TelegramUser(
        id=web_user.id,
        is_bot=False,
        first_name=web_user.first_name,
        last_name=web_user.last_name,
        username=web_user.username,
        language_code=web_user.language_code,
    )
    user = await UserService.get_or_create(session, tg_user)
    await session.commit()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is restricted")
    if _onboarding_gate_applies(request) and not await OnboardingService.is_complete(session, user.id):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "code": "onboarding_required",
                "version": settings.onboarding_version.strip() or "1",
            },
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_onboarded_user(
    user: CurrentUserDep,
    session: SessionDep,
) -> User:
    if not await OnboardingService.is_complete(session, user.id):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "code": "onboarding_required",
                "version": settings.onboarding_version.strip() or "1",
            },
        )
    return user


OnboardedUserDep = Annotated[User, Depends(get_onboarded_user)]
