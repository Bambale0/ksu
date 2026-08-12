from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Wallet, WalletTransaction
from app.services.profile_preferences import ProfilePreferenceService

router = APIRouter(prefix="/me", tags=["me"])


class UpdatePreferenceRequest(BaseModel):
    ui_language: str = Field(default="auto", max_length=16)
    notifications_enabled: bool = True
    marketing_notifications: bool = False
    profile_discoverable: bool = False


def _preference_view(preference) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "ui_language": preference.ui_language,
        "notifications_enabled": preference.notifications_enabled,
        "marketing_notifications": preference.marketing_notifications,
        "profile_discoverable": preference.profile_discoverable,
    }


@router.get("")
async def me(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    wallet = await session.get(Wallet, user.id)
    preference = await ProfilePreferenceService.get_or_create(session, user.id)
    await session.commit()
    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "balance_rox": str(wallet.balance if wallet else 0),
        "telegram_identity_read_only": True,
        "preferences": _preference_view(preference),
    }


@router.get("/preferences")
async def preferences(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    preference = await ProfilePreferenceService.get_or_create(session, user.id)
    await session.commit()
    return _preference_view(preference)


@router.put("/preferences")
async def update_preferences(
    payload: UpdatePreferenceRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    try:
        preference = await ProfilePreferenceService.update(
            session,
            user_id=user.id,
            ui_language=payload.ui_language,
            notifications_enabled=payload.notifications_enabled,
            marketing_notifications=payload.marketing_notifications,
            profile_discoverable=payload.profile_discoverable,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _preference_view(preference)


@router.get("/transactions")
async def transactions(user: CurrentUserDep, session: SessionDep) -> list[dict[str, object]]:
    rows = (
        await session.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user.id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "id": str(tx.id),
            "kind": tx.kind,
            "amount": str(tx.amount),
            "balance_after": str(tx.balance_after),
            "status": tx.status,
            "created_at": tx.created_at,
        }
        for tx in rows
    ]
