from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.services.discovery import DiscoveryService

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/home")
async def home_discovery(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    _ = user
    return await DiscoveryService.home(session)
