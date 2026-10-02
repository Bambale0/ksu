import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User as TelegramUser
from sqlalchemy import select

from app.db.models import User
from app.db.session import SessionFactory
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)


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

                    # A private inbound Telegram message proves that the bot may
                    # address this chat again. Recover deferred transactional
                    # deliveries before router ordering can consume the message.
                    incoming_message = event.message if isinstance(event, Update) else None
                    if (
                        existing_user is not None
                        and incoming_message is not None
                        and incoming_message.chat.type == "private"
                        and incoming_message.chat.id == event_user.id
                        and incoming_message.from_user is not None
                        and incoming_message.from_user.id == event_user.id
                    ):
                        recovered = await NotificationDeliveryService.requeue_reachable_user_deliveries(
                            session,
                            user_id=existing_user.id,
                        )
                        if recovered:
                            logger.info(
                                "notification_deliveries_requeued_after_user_contact",
                                extra={
                                    "telegram_user_id": event_user.id,
                                    "recovered_deliveries": recovered,
                                },
                            )
                            # Persist reachability independently of the downstream
                            # command/FSM handler so a later handler error cannot
                            # lose the recovery signal.
                            await session.commit()

                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
