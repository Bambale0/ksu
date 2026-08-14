from fastapi import APIRouter

from app.api.v1 import (
    admin_accounts,
    admin_audit,
    admin_auth,
    admin_capabilities,
    admin_control,
    admin_creator_partnership,
    admin_operations,
    admin_payments,
    admin_users,
    card_payments,
    creator_partnership,
    discovery,
    feed,
    generations,
    me,
    media,
    music_generations,
    notifications,
    onboarding,
    payments,
    promocodes,
    prompt_tools,
    reference_presets,
    referrals,
    social,
    support,
    trends,
    uploads,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(me.router)
api_router.include_router(onboarding.router)
api_router.include_router(promocodes.router)
api_router.include_router(referrals.router)
api_router.include_router(creator_partnership.router)
# Music overrides only the shared generation catalog/quote/create/history read routes.
# It is registered first so Suno can remain a first-class audio domain while old
# image/video contracts keep their original implementation untouched.
api_router.include_router(music_generations.router)
api_router.include_router(generations.router)
api_router.include_router(discovery.router)
api_router.include_router(feed.router)
api_router.include_router(trends.router)
api_router.include_router(prompt_tools.router)
api_router.include_router(reference_presets.router)
api_router.include_router(media.router)
api_router.include_router(card_payments.router)
api_router.include_router(payments.router)
api_router.include_router(notifications.router)
api_router.include_router(social.router)
api_router.include_router(support.router)
api_router.include_router(uploads.router)
api_router.include_router(admin_auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_operations.router)
api_router.include_router(admin_payments.router)
api_router.include_router(admin_accounts.router)
api_router.include_router(admin_audit.router)
api_router.include_router(admin_capabilities.router)
api_router.include_router(admin_control.router)
api_router.include_router(admin_creator_partnership.router)