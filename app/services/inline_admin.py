from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, User
from app.services.admin_security import parse_bootstrap_ids


async def ensure_bootstrap_admin(
    session: AsyncSession,
    user: User,
) -> AdminAccount | None:
    """Materialize ENV-provisioned admins after trusted Telegram authentication.

    CurrentUserDep has already verified Telegram WebApp initData, so user.telegram_id
    is a trusted identity. Only IDs explicitly listed in ADMIN_BOOTSTRAP_TELEGRAM_IDS
    are eligible. Existing rows are never reactivated here: explicit revocation in the
    admin domain must win over bootstrap configuration.
    """

    if int(user.telegram_id) not in parse_bootstrap_ids():
        return None

    account = await session.scalar(select(AdminAccount).where(AdminAccount.user_id == user.id))
    if account is not None:
        return account

    # Serialize only the first-use bootstrap for the same Telegram user. Existing
    # admins take the fast path above and do not lock their user row on every API call.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    account = await session.scalar(select(AdminAccount).where(AdminAccount.user_id == user.id))
    if account is not None:
        return account

    account = AdminAccount(user_id=user.id, role="owner", is_active=True)
    session.add(account)
    await session.flush()
    return account
