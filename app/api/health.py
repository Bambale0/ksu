from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.core.config import settings
from app.core.observability import worker_health
from app.core.runtime_services import OPERATIONAL_WORKERS
from app.db.session import SessionFactory

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        await request.app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Dependencies are not ready") from exc
    return {"status": "ready"}


@router.get("/telegram")
async def telegram_contract(request: Request) -> dict[str, object]:
    """Expose the non-secret Telegram contract needed by Main Mini App deep links.

    ``getMe().has_main_web_app`` is runtime state controlled by BotFather rather
    than repository code. Keeping it observable makes BOT_INVALID diagnosable
    without exposing the bot token or relying on deployment logs.
    """

    configured = bool(settings.bot_token)
    username = str(settings.bot_username or "").strip().lstrip("@") or None
    main_mini_app_enabled = bool(
        getattr(request.app.state, "bot_has_main_web_app", False)
    )
    return {
        "status": (
            "ok"
            if not configured or main_mini_app_enabled
            else "misconfigured"
        ),
        "bot_configured": configured,
        "bot_username": username,
        "main_mini_app_enabled": main_mini_app_enabled,
        "main_mini_app_link_template": (
            f"https://t.me/{username}?startapp=<payload>" if username else None
        ),
    }


@router.get("/operational")
async def operational(request: Request) -> dict[str, object]:
    workers = [
        await worker_health(request.app.state.redis, worker)
        for worker in OPERATIONAL_WORKERS
    ]
    if not all(bool(item["up"]) for item in workers):
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "workers": workers},
        )
    return {"status": "operational", "workers": workers}
