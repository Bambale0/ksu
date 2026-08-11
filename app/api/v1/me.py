from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import Wallet, WalletTransaction

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def me(user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    wallet = await session.get(Wallet, user.id)
    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "balance_rox": str(wallet.balance if wallet else 0),
    }


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
