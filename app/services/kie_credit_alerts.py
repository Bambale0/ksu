from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdminAccount, User
from app.providers.kie_credits import KieCreditClient

logger = logging.getLogger(__name__)

ALERT_STATE_KEY = "alerts:kie:credits:state"
ALERT_REPEAT_KEY = "alerts:kie:credits:repeat"
ALERT_ROLES = frozenset({"owner", "admin", "finance"})


class KieCreditAlertService:
    @staticmethod
    def _format_credits(value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _alert_state(credits: Decimal) -> str | None:
        threshold = Decimal(settings.kie_credit_alert_threshold)
        if credits <= 0:
            return "depleted"
        if credits <= threshold:
            return "low"
        return None

    @classmethod
    async def recipient_ids(cls, session: AsyncSession) -> list[int]:
        rows = await session.scalars(
            select(User.telegram_id)
            .join(AdminAccount, AdminAccount.user_id == User.id)
            .where(
                AdminAccount.is_active.is_(True),
                User.is_active.is_(True),
                AdminAccount.role.in_(ALERT_ROLES),
            )
            .order_by(User.telegram_id)
        )
        return sorted({int(value) for value in rows.all()})

    @classmethod
    def _message(cls, credits: Decimal, state: str) -> str:
        threshold = cls._format_credits(Decimal(settings.kie_credit_alert_threshold))
        current = cls._format_credits(credits)
        if state == "depleted":
            return (
                "⚠️ Kie: кредиты закончились\n\n"
                f"Остаток: {current}\n"
                f"Порог предупреждения: {threshold}\n\n"
                "Генерации через Kie могут перестать запускаться. Пополните баланс провайдера."
            )
        return (
            "⚠️ Kie: мало кредитов\n\n"
            f"Остаток: {current}\n"
            f"Порог предупреждения: {threshold}\n\n"
            "Проверьте расход и пополните баланс до остановки генераций."
        )

    @classmethod
    def _recovery_message(cls, credits: Decimal) -> str:
        return (
            "✅ Kie: баланс восстановлен\n\n"
            f"Текущий остаток: {cls._format_credits(credits)} кредитов."
        )

    @staticmethod
    async def _send(bot: Bot, recipients: list[int], *, text: str) -> int:
        sent = 0
        for telegram_id in recipients:
            try:
                await bot.send_message(chat_id=telegram_id, text=text)
                sent += 1
            except TelegramForbiddenError:
                logger.warning(
                    "kie_credit_alert_admin_unreachable",
                    extra={"telegram_id": telegram_id},
                )
            except TelegramRetryAfter as exc:
                logger.warning(
                    "kie_credit_alert_retry_after",
                    extra={"telegram_id": telegram_id, "retry_after": int(exc.retry_after)},
                )
            except TelegramAPIError:
                logger.exception(
                    "kie_credit_alert_telegram_api_error",
                    extra={"telegram_id": telegram_id},
                )
        return sent

    @classmethod
    async def check_once(
        cls,
        *,
        session: AsyncSession,
        redis: Redis,
        bot: Bot,
        client: KieCreditClient,
    ) -> Decimal:
        balance = await client.get_remaining_credits()
        credits = balance.credits
        recipients = await cls.recipient_ids(session)
        if not recipients:
            logger.warning("kie_credit_alert_no_active_admin_recipients")
            return credits

        state = cls._alert_state(credits)
        previous_raw = await redis.get(ALERT_STATE_KEY)
        previous = str(previous_raw) if previous_raw else None

        if state is None:
            if previous:
                await redis.delete(ALERT_STATE_KEY, ALERT_REPEAT_KEY)
                await cls._send(bot, recipients, text=cls._recovery_message(credits))
            return credits

        repeat_raw = await redis.get(ALERT_REPEAT_KEY)
        repeat_state = str(repeat_raw) if repeat_raw else None
        should_send = previous != state or repeat_state != state

        await redis.set(ALERT_STATE_KEY, state)
        if should_send:
            repeat_seconds = max(60, int(settings.kie_credit_alert_repeat_seconds))
            await redis.set(ALERT_REPEAT_KEY, state, ex=repeat_seconds)
            await cls._send(bot, recipients, text=cls._message(credits, state))
        return credits
