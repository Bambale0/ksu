from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.bot.handlers import launcher
from app.bot.middlewares import DatabaseSessionMiddleware


def create_dispatcher(redis: Redis) -> Dispatcher:
    """Telegram is only the transport/launcher; all customer UI lives in Mini App."""
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(launcher.router)
    return dispatcher
