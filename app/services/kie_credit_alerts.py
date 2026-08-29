from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from redis.asyncio import Redis

from app.core.config import settings
from app.providers.kie import KieClient, KieProviderError
from app.services.admin_security import parse_bootstrap_ids

logger = logging.getLogger(__name__)

ALERT_STATE_KEY = "alerts:kie:credits:state"


class KieCreditAlertService:
    @staticmethod
    def _format_credits(value: Decimal) -> str:
        return f"{value:f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def is_configured() -> bool:
        return bool(
            settings.kie_credit_alert_enabled
            and settings.kie_api_key
            and settings.bot_token
            and parse_bootstrap_ids()
        )

    @staticmethod
    def _alert_state(credits: Decimal) -> str | None:
        threshold = Decimal(settings.kie_credit_alert_threshold)
        if credits <= 0:
            return "depleted"
        if credits <= threshold:
            return "low"
        return None

    @classmethod
    def _message(cls, credits: Decimal, state: str) -> str:
        if state == "depleted":
            title = "Kie credits exhausted"
            action = "Генерации через Kie могут перестать приниматься. Пополните баланс Kie."
        else:
            title = "Kie credits are low"
            action = "Проверьте расход и пополните баланс Kie до остановки генераций."
        return (
            f"⚠️ {title}\n\n"
            f"Остаток кредитов Kie: {cls._format_credits(credits)}\n"
            f"Порог алерта: {cls._format_credits(Decimal(settings.kie_credit_alert_threshold))}\n\n"
            f"{action}"
        )

    @staticmethod
    async def _send_admin_alert(bot: Bot, *, text: str) -> None:
        for telegram_id in sorted(parse_bootstrap_ids()):
            try:
                await bot.send_message(chat_id=telegram_id, text=text)
            except TelegramForbiddenError:
                logger.warning("kie_credit_alert_admin_unreachable", extra={"telegram_id": telegram_id})
            except TelegramRetryAfter as exc:
                logger.warning(
                    "kie_credit_alert_retry_after",
                    extra={"telegram_id": telegram_id, "retry_after": int(exc.retry_after)},
                )
            except TelegramAPIError:
                logger.exception("kie_credit_alert_telegram_api_error", extra={"telegram_id": telegram_id})

    @classmethod
    async def check_once(
        cls,
        *,
        redis: Redis,
        bot: Bot,
        client: KieClient,
    ) -> Decimal | None:
        if not cls.is_configured():
            return None

        try:
            balance = await client.get_remaining_credits()
        except KieProviderError:
            logger.exception("kie_credit_alert_check_failed")
            return None
        except Exception:
            logger.exception("kie_credit_alert_unexpected_check_error")
            return None

        state = cls._alert_state(balance.credits)
        if state is None:
            previous = await redis.get(ALERT_STATE_KEY)
            if previous:
                await redis.delete(ALERT_STATE_KEY)
                await cls._send_admin_alert(
                    bot,
                    text=(
                        "✅ Kie credits recovered\n\n"
                        f"Текущий остаток кредитов Kie: {cls._format_credits(balance.credits)}"
                    ),
                )
            return balance.credits

        previous = await redis.get(ALERT_STATE_KEY)
        if previous == state:
            return balance.credits

        await redis.set(
            ALERT_STATE_KEY,
            state,
            ex=max(60, int(settings.kie_credit_alert_repeat_seconds)),
        )
        await cls._send_admin_alert(bot, text=cls._message(balance.credits, state))
        return balance.credits
