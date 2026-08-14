from decimal import Decimal

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, User
from app.services.wallet import WalletService


class UserService:
    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
        return await session.scalar(select(User).where(User.telegram_id == telegram_id))

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
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            user.language_code = telegram_user.language_code
            return user

        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
        )
        session.add(user)
        await session.flush()
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
