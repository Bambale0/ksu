from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.services.onboarding import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("")
async def onboarding_status(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    return await OnboardingService.status(session, user.id)


@router.post("/complete")
async def complete_onboarding(
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    await OnboardingService.complete(session, user.id)
    await session.commit()
    return await OnboardingService.status(session, user.id)
