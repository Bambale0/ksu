from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.core.observability import worker_health
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


@router.get("/operational")
async def operational(request: Request) -> dict[str, object]:
    workers = [
        await worker_health(request.app.state.redis, "generation-worker"),
        await worker_health(request.app.state.redis, "payment-worker"),
        await worker_health(request.app.state.redis, "media-worker"),
    ]
    if not all(bool(item["up"]) for item in workers):
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "workers": workers},
        )
    return {"status": "operational", "workers": workers}
