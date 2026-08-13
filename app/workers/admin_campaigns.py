from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, select

from app.core.config import settings
from app.db.admin_models import NotificationCampaign, NotificationCampaignDelivery
from app.db.models import User
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.services.admin_delivery import CampaignDeliveryService

logger = logging.getLogger(__name__)


def _campaign_text(campaign: NotificationCampaign) -> str:
    title = str((campaign.message or {}).get("title") or "").strip()
    body = str((campaign.message or {}).get("body") or "").strip()
    return f"{title}\n\n{body}" if title and body else title or body


async def _maybe_complete_campaign(session, campaign_id: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    active = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(NotificationCampaignDelivery)
                .where(
                    NotificationCampaignDelivery.campaign_id == campaign_id,
                    NotificationCampaignDelivery.status.in_(["pending", "retry", "sending"]),
                )
            )
        )
        or 0
    )
    if active:
        return
    campaign = await session.get(NotificationCampaign, campaign_id, with_for_update=True)
    if campaign is not None and campaign.status == "running":
        campaign.status = "completed"


async def _process(bot: Bot, delivery_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        row = await session.get(NotificationCampaignDelivery, delivery_id, with_for_update=True)
        if row is None or row.status != "sending":
            return
        campaign = await session.get(NotificationCampaign, row.campaign_id)
        if campaign is None or campaign.status == "cancelled":
            CampaignDeliveryService.terminal(row, status="cancelled", error="campaign_cancelled")
            await session.commit()
            return
        user = await session.get(User, row.user_id)
        if user is None or not user.is_active:
            CampaignDeliveryService.terminal(
                row,
                status="undeliverable",
                error="user_inactive_or_missing",
            )
            await _maybe_complete_campaign(session, row.campaign_id)
            await session.commit()
            return
        preference = await session.get(UserPreference, user.id)
        if preference is not None and (
            not preference.notifications_enabled or not preference.marketing_notifications
        ):
            CampaignDeliveryService.terminal(
                row,
                status="suppressed",
                error="marketing_notifications_disabled",
            )
            await _maybe_complete_campaign(session, row.campaign_id)
            await session.commit()
            return
        try:
            sent = await bot.send_message(chat_id=user.telegram_id, text=_campaign_text(campaign))
        except TelegramForbiddenError as exc:
            CampaignDeliveryService.terminal(
                row,
                status="undeliverable",
                error=f"telegram_forbidden:{exc}",
            )
        except TelegramRetryAfter as exc:
            CampaignDeliveryService.retry(
                row,
                error=f"telegram_retry_after:{exc}",
                retry_after=int(exc.retry_after),
            )
        except TelegramAPIError as exc:
            CampaignDeliveryService.retry(row, error=f"telegram_api:{exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("admin_campaign_delivery_error", extra={"delivery_id": str(row.id)})
            CampaignDeliveryService.retry(
                row,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )
        else:
            CampaignDeliveryService.sent(row, external_message_id=str(sent.message_id))
        await _maybe_complete_campaign(session, row.campaign_id)
        await session.commit()


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for the admin campaign worker")
    bot = Bot(settings.bot_token)
    try:
        while True:
            async with SessionFactory() as session:
                claimed = await CampaignDeliveryService.claim_batch(session)
                ids = [row.id for row in claimed]
                await session.commit()
            if not ids:
                await asyncio.sleep(settings.campaign_worker_poll_seconds)
                continue
            for delivery_id in ids:
                await _process(bot, delivery_id)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
