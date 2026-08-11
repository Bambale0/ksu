from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import settings
from app.services.referrals import ReferralService

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/stats")
async def stats(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    result = await ReferralService.stats(session, user.id)
    return {
        **result,
        "first_line_percent": str(settings.referral_first_percent),
        "second_line_percent": str(settings.referral_second_percent),
        "referral_payload": f"ref_{user.telegram_id}",
    }
