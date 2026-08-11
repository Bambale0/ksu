from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionFactory


class DatabaseSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionFactory() as session:
            data["session"] = session
            try:
                event_user = data.get("event_from_user")
                if isinstance(event_user, TelegramUser):
                    existing_user = await session.scalar(
                        select(User).where(User.telegram_id == event_user.id)
                    )
                    if existing_user is not None and not existing_user.is_active:
                        return None

                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
