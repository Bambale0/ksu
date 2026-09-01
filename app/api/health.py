from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.core.config import settings
from app.core.observability import worker_health
from app.db.session import SessionFactory

router = APIRouter(prefix="/health", tags=["health"])

OPERATIONAL_WORKERS = (
    "generation-worker",
    "payment-worker",
    "media-worker",
    "prompt-tool-worker",
    "notification-worker",
    "admin-support-worker",
    "admin-campaign-worker",
    "creator-partnership-worker",
    "kie-credit-alert-worker",
)


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
    """Expose the non-secret Telegram contract used by ROXY public deep links."""

    configured = bool(settings.bot_token)
    username = str(settings.bot_username or "").strip().lstrip("@") or None
    short_name = str(settings.telegram_mini_app_short_name or "").strip().strip("/") or None
    main_mini_app_enabled = bool(
        getattr(request.app.state, "bot_has_main_web_app", False)
    )
    ready_for_public_links = bool(username)
    main_template = f"https://t.me/{username}?startapp=<payload>" if username else None
    return {
        "status": (
            "ok"
            if not configured or ready_for_public_links
            else "misconfigured"
        ),
        "bot_configured": configured,
        "bot_username": username,
        "mini_app_short_name": short_name,
        "direct_mini_app_link_template": main_template,
        "named_mini_app_link_template": (
            f"https://t.me/{username}/{short_name}?startapp=<payload>"
            if username and short_name
            else None
        ),
        "bot_start_link_template": (
            f"https://t.me/{username}?start=<payload>" if username else None
        ),
        "main_mini_app_enabled": main_mini_app_enabled,
        "main_mini_app_link_template": main_template,
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
