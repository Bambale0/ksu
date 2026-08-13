from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api.card_webhooks import router as card_webhook_router
from app.api.health import router as health_router
from app.api.internal_admin import router as internal_admin_router
from app.api.metrics import router as metrics_router
from app.api.router import api_router
from app.api.v1.batches import router as batch_router
from app.api.v1.partner_approval import router as partner_approval_router
from app.api.webhooks import router as webhook_router
from app.bot.dispatcher import create_dispatcher
from app.core.config import settings
from app.core.http_observability import RequestObservabilityMiddleware
from app.core.http_security import SecurityHeadersMiddleware
from app.core.logging import configure_logging
from app.core.observability import configure_telemetry, shutdown_telemetry
from app.db.session import engine
from app.services.abuse_protection import ProtectionBackendUnavailable, ResourcePolicyError
from app.services.notification_events import register_notification_events

configure_logging()
register_notification_events()


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
        shutdown_telemetry()


app = FastAPI(
    title="KSU API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestObservabilityMiddleware)
configure_telemetry(app)


@app.exception_handler(ResourcePolicyError)
async def resource_policy_error(_request: Request, exc: ResourcePolicyError) -> JSONResponse:
    status_code = 503 if isinstance(exc, ProtectionBackendUnavailable) else 429
    return JSONResponse(
        status_code=status_code,
        headers={"Retry-After": str(exc.retry_after)},
        content={
            "detail": str(exc),
            "code": exc.code,
            "retry_after": exc.retry_after,
        },
    )


app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(webhook_router)
app.include_router(card_webhook_router)
app.include_router(internal_admin_router)
app.include_router(api_router)
app.include_router(batch_router, prefix="/api/v1")
app.include_router(partner_approval_router, prefix="/api/v1")

web_dir = Path(__file__).resolve().parent / "web"
mini_app_dir = web_dir / "mini_app"
admin_app_dir = web_dir / "admin_app"
app.mount("/mini-app", StaticFiles(directory=mini_app_dir, html=True), name="mini-app")
app.mount("/admin-app", StaticFiles(directory=admin_app_dir, html=True), name="admin-app")
