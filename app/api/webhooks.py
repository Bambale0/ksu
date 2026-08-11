from fastapi import APIRouter, Header, HTTPException, Request, status
from aiogram.types import Update

from app.core.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.telegram_webhook_secret and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update, redis=request.app.state.redis)
    return {"ok": True}
