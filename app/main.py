from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.health import router as health_router
from app.api.router import api_router
from app.api.webhooks import router as webhook_router
from app.bot.dispatcher import create_dispatcher
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    app.state.bot = None
    app.state.dispatcher = None

    if settings.bot_token:
        bot = Bot(settings.bot_token)
        dispatcher = create_dispatcher(redis)
        app.state.bot = bot
        app.state.dispatcher = dispatcher
        if settings.telegram_webhook_url:
            webhook_url = f"{settings.telegram_webhook_url.rstrip('/')}/webhooks/telegram"
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )

    try:
        yield
    finally:
        dispatcher = app.state.dispatcher
        bot = app.state.bot
        if dispatcher is not None:
            await dispatcher.storage.close()
        if bot is not None:
            await bot.session.close()
        await redis.aclose()
        await engine.dispose()


app = FastAPI(
    title="KSU API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(api_router)
