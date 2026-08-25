from decimal import Decimal

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.services.referral_antifraud import ReferralAntifraudService
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

        # A Mini App cold boot fan-outs several authenticated requests at once.
        # Make creation atomic in PostgreSQL instead of relying on SELECT -> INSERT,
        # which can race for users.telegram_id and surface intermittent HTTP 500s.
        result = await session.execute(
            insert(User)
            .values(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=[User.telegram_id])
            .returning(User.id)
        )
        created_user_id = result.scalar_one_or_none()
        await session.flush()

        user = await cls.get_by_telegram_id(session, telegram_user.id)
        if user is None:
            raise RuntimeError("Unable to initialize Telegram user")
        cls._sync_telegram_profile(user, telegram_user)

        if created_user_id is None:
            # The concurrent creator owns wallet/welcome/referral initialization.
            # ON CONFLICT waits for that transaction to resolve before this branch.
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

        await ReferralAntifraudService.attach_new_user(
            session,
            visitor=user,
            inviter_telegram_id=inviter_telegram_id,
        )
        return user
