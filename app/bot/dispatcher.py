from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.bot.handlers import admin, admin_extensions, launcher
from app.bot.middlewares import DatabaseSessionMiddleware


def create_dispatcher(redis: Redis) -> Dispatcher:
    """Customer UX is Mini-App-only; Telegram admin routes remain operator-only."""
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())

    # Keep trusted operator commands reachable without exposing the retired
    # customer text menus. Register them before the customer catch-all launcher.
    dispatcher.include_router(admin.router)
    dispatcher.include_router(admin_extensions.router)
    dispatcher.include_router(launcher.router)
    return dispatcher
