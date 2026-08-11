from fastapi import APIRouter

from app.api.v1 import generations, me, promocodes, referrals, support

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(me.router)
api_router.include_router(promocodes.router)
api_router.include_router(referrals.router)
api_router.include_router(generations.router)
api_router.include_router(support.router)
