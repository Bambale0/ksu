from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.bot.handlers import generation, start, support
from app.bot.middlewares import DatabaseSessionMiddleware


def create_dispatcher(redis: Redis) -> Dispatcher:
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(generation.router)
    dispatcher.include_router(support.router)
    return dispatcher
