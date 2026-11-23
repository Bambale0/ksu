"""Verified provider identities, immutable owners and explicit account linking."""
from __future__ import annotations

import uuid

from aiogram.types import User as TelegramUser
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.web_auth_models import WebIdentity
from app.services.users import UserService
from app.services.wallet import WalletService


async def verified_web_identity(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    display_name: str,
    display_email: str | None,
    link_user_id: uuid.UUID | None = None,
) -> User:
    """Never merge two accounts based on matching email or display name.

    An explicit link requires an authenticated session and a fresh, verified
    proof from the provider. Provider collisions fail with 409.
    """
    if provider not in {"email", "yandex"} or not subject:
        raise ValueError("Unknown identity provider")

    row = await session.scalar(
        select(WebIdentity).where(
            WebIdentity.provider == provider,
            WebIdentity.subject == subject,
        ).with_for_update(),
    )
    if row:
        if link_user_id and row.user_id != link_user_id:
            raise HTTPException(409, "This identity is connected to another account")
        user = await session.get(User, row.user_id)
        if not user or not user.is_active:
            raise HTTPException(403, "Account unavailable")
        return user

    if link_user_id:
        user = await session.get(User, link_user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "Account unavailable")
    else:
        user = User(
            telegram_id=None,
            first_name=(display_name.strip() or "ROXY")[:255],
            last_name=None,
            username=None,
            language_code="ru",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)

    session.add(WebIdentity(
        user_id=user.id,
        provider=provider,
        subject=subject,
        display_email=display_email[:320] if display_email else None,
    ))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # A concurrent login/link cannot silently claim another user.
        existing = await session.scalar(
            select(WebIdentity).where(
                WebIdentity.provider == provider,
                WebIdentity.subject == subject,
            ),
        )
        if existing and not link_user_id:
            found = await session.get(User, existing.user_id)
            if found and found.is_active:
                return found
        raise HTTPException(409, "Identity already connected") from exc
    return user


async def verified_telegram_identity(
    session: AsyncSession,
    *,
    verified_user: dict[str, object],
    link_user_id: uuid.UUID | None = None,
) -> User:
    telegram_id = int(verified_user["id"])
    existing = await UserService.get_by_telegram_id(session, telegram_id)
    if link_user_id is not None:
        owner = await session.get(User, link_user_id)
        if owner is None or not owner.is_active:
            raise HTTPException(403, "Account unavailable")
        if existing is not None and existing.id != owner.id:
            raise HTTPException(409, "Telegram is already connected to another account")
        if owner.telegram_id is not None and owner.telegram_id != telegram_id:
            raise HTTPException(409, "Another Telegram account is already connected")
        if owner.telegram_id is None:
            owner.telegram_id = telegram_id
        owner.username = str(verified_user.get("username") or "") or None
        if not owner.first_name or owner.first_name == "ROXY":
            owner.first_name = str(verified_user.get("first_name") or "ROXY")[:255]
        await session.commit()
        return owner

    tg_user = TelegramUser(
        id=telegram_id,
        is_bot=False,
        first_name=str(verified_user.get("first_name") or "ROXY"),
        last_name=str(verified_user.get("last_name") or "") or None,
        username=str(verified_user.get("username") or "") or None,
        language_code="ru",
    )
    user = await UserService.get_or_create(session, tg_user)
    await session.commit()
    if not user.is_active:
        raise HTTPException(403, "Account unavailable")
    return user
