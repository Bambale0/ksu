from fastapi import APIRouter

from app.api.v1 import (
    admin_accounts,
    admin_audit,
    admin_auth,
    admin_operations,
    admin_payments,
    admin_users,
    generations,
    me,
    media,
    payments,
    promocodes,
    referrals,
    support,
    uploads,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(me.router)
api_router.include_router(promocodes.router)
api_router.include_router(referrals.router)
api_router.include_router(generations.router)
api_router.include_router(media.router)
api_router.include_router(payments.router)
api_router.include_router(support.router)
api_router.include_router(uploads.router)
api_router.include_router(admin_auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_operations.router)
api_router.include_router(admin_payments.router)
api_router.include_router(admin_accounts.router)
api_router.include_router(admin_audit.router)
