from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.broadcast_models import BroadcastCampaign, BroadcastRecipient
from app.db.models import User
from app.db.notification_models import NotificationDelivery
from app.db.profile_models import UserPreference
from app.services.notifications import NotificationService


def utcnow() -> datetime:
    return datetime.now(UTC)


class BroadcastCampaignError(ValueError):
    pass


class BroadcastService:
    @staticmethod
    def _eligible_query():
        return (
            select(User.id)
            .join(UserPreference, UserPreference.user_id == User.id)
            .where(
                User.is_active.is_(True),
                UserPreference.notifications_enabled.is_(True),
                UserPreference.marketing_notifications.is_(True),
            )
        )

    @classmethod
    async def eligible_count(cls, session: AsyncSession) -> int:
        query = cls._eligible_query().subquery()
        return int((await session.scalar(select(func.count()).select_from(query))) or 0)

    @classmethod
    async def create_draft(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        title: str,
        body: str,
    ) -> BroadcastCampaign:
        title = title.strip()
        body = body.strip()
        if not title or len(title) > 160:
            raise BroadcastCampaignError("Campaign title must contain 1-160 characters")
        if not body or len(body) > 4000:
            raise BroadcastCampaignError("Campaign body must contain 1-4000 characters")
        campaign = BroadcastCampaign(
            created_by_admin_id=admin_id,
            title=title,
            body=body,
            status="draft",
            audience_json={
                "active_only": True,
                "notifications_enabled": True,
                "marketing_notifications": True,
            },
        )
        session.add(campaign)
        await session.flush()
        return campaign

    @classmethod
    async def launch(
        cls,
        session: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> BroadcastCampaign:
        campaign = await session.scalar(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.id == campaign_id)
            .with_for_update()
        )
        if campaign is None:
            raise LookupError("Campaign not found")
        if campaign.status != "draft":
            raise BroadcastCampaignError("Only a draft campaign can be launched")
        campaign.eligible_count = await cls.eligible_count(session)
        campaign.status = "queued"
        campaign.started_at = utcnow()
        campaign.cursor_user_id = None
        await session.flush()
        return campaign

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> BroadcastCampaign:
        campaign = await session.scalar(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.id == campaign_id)
            .with_for_update()
        )
        if campaign is None:
            raise LookupError("Campaign not found")
        if campaign.status in {"fanout_complete", "canceled"}:
            if campaign.status == "canceled":
                return campaign
            raise BroadcastCampaignError("Completed campaign cannot be canceled")
        campaign.status = "canceled"
        campaign.canceled_at = utcnow()
        await session.flush()
        return campaign

    @classmethod
    async def fanout_once(cls, session: AsyncSession) -> int:
        campaign = await session.scalar(
            select(BroadcastCampaign)
            .where(BroadcastCampaign.status.in_(["queued", "dispatching"]))
            .order_by(BroadcastCampaign.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if campaign is None:
            return 0
        campaign.status = "dispatching"

        user_query = cls._eligible_query()
        if campaign.cursor_user_id is not None:
            user_query = user_query.where(User.id > campaign.cursor_user_id)
        user_ids = list(
            (
                await session.scalars(
                    user_query.order_by(User.id.asc()).limit(settings.broadcast_fanout_batch_size)
                )
            ).all()
        )
        if not user_ids:
            campaign.status = "fanout_complete"
            campaign.fanout_completed_at = utcnow()
            await session.flush()
            return 0

        created = 0
        for user_id in user_ids:
            existing = await session.scalar(
                select(BroadcastRecipient.id).where(
                    BroadcastRecipient.campaign_id == campaign.id,
                    BroadcastRecipient.user_id == user_id,
                )
            )
            if existing is not None:
                continue
            notification = await NotificationService.create(
                session,
                user_id=user_id,
                kind="marketing_campaign",
                title=campaign.title,
                body=campaign.body,
                purpose="marketing",
            )
            session.add(
                BroadcastRecipient(
                    campaign_id=campaign.id,
                    user_id=user_id,
                    notification_id=notification.id,
                )
            )
            created += 1

        campaign.cursor_user_id = user_ids[-1]
        campaign.queued_count += created
        await session.flush()
        return created

    @staticmethod
    async def delivery_summary(
        session: AsyncSession,
        campaign_id: uuid.UUID,
    ) -> dict[str, int]:
        rows = (
            await session.execute(
                select(NotificationDelivery.status, func.count())
                .join(
                    BroadcastRecipient,
                    BroadcastRecipient.notification_id == NotificationDelivery.notification_id,
                )
                .where(BroadcastRecipient.campaign_id == campaign_id)
                .group_by(NotificationDelivery.status)
            )
        ).all()
        return {str(status): int(count) for status, count in rows}

    @classmethod
    async def view(cls, session: AsyncSession, campaign: BroadcastCampaign) -> dict[str, Any]:
        deliveries = await cls.delivery_summary(session, campaign.id)
        return {
            "id": str(campaign.id),
            "title": campaign.title,
            "body": campaign.body,
            "status": campaign.status,
            "audience": campaign.audience_json,
            "eligible_count": campaign.eligible_count,
            "queued_count": campaign.queued_count,
            "deliveries": deliveries,
            "created_by_admin_id": str(campaign.created_by_admin_id) if campaign.created_by_admin_id else None,
            "created_at": campaign.created_at.isoformat(),
            "updated_at": campaign.updated_at.isoformat(),
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "fanout_completed_at": campaign.fanout_completed_at.isoformat() if campaign.fanout_completed_at else None,
            "canceled_at": campaign.canceled_at.isoformat() if campaign.canceled_at else None,
        }
