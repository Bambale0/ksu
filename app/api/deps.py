from typing import Annotated

from aiogram.types import User as TelegramUser
from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.db.session import get_session
from app.services.users import UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]


async def get_current_user(
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
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
