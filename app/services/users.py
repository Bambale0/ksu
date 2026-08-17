from decimal import Decimal

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, User
from app.services.wallet import WalletService


class UserService:
    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
        return await session.scalar(select(User).where(User.telegram_id == telegram_id))

    @staticmethod
    def _sync_telegram_profile(user: User, telegram_user: TelegramUser) -> None:
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        user.language_code = telegram_user.language_code

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        telegram_user: TelegramUser,
        *,
        inviter_telegram_id: int | None = None,
    ) -> User:
        user = await cls.get_by_telegram_id(session, telegram_user.id)
        if user is not None:
            cls._sync_telegram_profile(user, telegram_user)
            return user

        candidate = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
        )
        created = False
        try:
            # Mini App startup issues several authenticated requests in parallel. Two
            # fresh requests can both miss the initial SELECT, so isolate the INSERT
            # behind a savepoint. A uniqueness race then rolls back only this insert,
            # not the caller's whole transaction.
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
            user = candidate
            created = True
        except IntegrityError:
            # PostgreSQL waits for the competing unique-key transaction before
            # resolving the INSERT. Once it reports the conflict, READ COMMITTED can
            # see the winner on this new statement.
            user = await cls.get_by_telegram_id(session, telegram_user.id)
            if user is None:
                raise
            cls._sync_telegram_profile(user, telegram_user)

        if not created:
            return user

        await WalletService.ensure_wallet(session, user.id)

        if settings.start_balance_rox > Decimal("0"):
            await WalletService.credit(
                session,
                user_id=user.id,
                amount=settings.start_balance_rox,
                kind="welcome_bonus",
                idempotency_key=f"welcome:{user.id}",
            )

        if inviter_telegram_id and inviter_telegram_id != telegram_user.id:
            inviter = await cls.get_by_telegram_id(session, inviter_telegram_id)
            if inviter is not None:
                session.add(
                    ReferralRelation(referred_user_id=user.id, inviter_user_id=inviter.id)
                )
                if settings.invite_bonus_rox > Decimal("0"):
                    await WalletService.credit(
                        session,
                        user_id=inviter.id,
                        amount=settings.invite_bonus_rox,
                        kind="referral_invite_bonus",
                        reference_type="referral_user",
                        reference_id=str(user.id),
                        idempotency_key=f"invite-bonus:{user.id}",
                    )

        return user
