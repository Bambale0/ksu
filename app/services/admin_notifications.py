from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import NotificationCampaign, NotificationCampaignDelivery
from app.db.models import AdminAccount, Notification, User
from app.db.notification_models import NotificationDelivery
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy

ALLOWED_SEGMENT_KEYS = frozenset({"active_only", "user_ids", "language_codes"})


class CampaignValidationError(ValueError):
    pass


def validate_campaign_segment(segment: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(segment or {})
    unknown = sorted(set(value) - ALLOWED_SEGMENT_KEYS)
    if unknown:
        raise CampaignValidationError(f"Unknown campaign segment keys: {', '.join(unknown)}")
    if "active_only" in value and not isinstance(value["active_only"], bool):
        raise CampaignValidationError("active_only must be boolean")
    if "user_ids" in value:
        if not isinstance(value["user_ids"], list) or len(value["user_ids"]) > 10_000:
            raise CampaignValidationError("user_ids must be a list with at most 10000 items")
        try:
            value["user_ids"] = [str(uuid.UUID(str(item))) for item in value["user_ids"]]
        except ValueError as exc:
            raise CampaignValidationError("user_ids contains invalid UUID") from exc
    if "language_codes" in value:
        languages = value["language_codes"]
        if not isinstance(languages, list) or not languages or len(languages) > 50:
            raise CampaignValidationError("language_codes must be a non-empty list")
        value["language_codes"] = [str(item)[:16] for item in languages]
    return value


def validate_campaign_message(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise CampaignValidationError("Campaign message must be an object")
    title = str(message.get("title") or "").strip()
    body = str(message.get("body") or "").strip()
    if not title or len(title) > 255:
        raise CampaignValidationError("Campaign title must contain 1..255 characters")
    if not body or len(body) > 4000:
        raise CampaignValidationError("Campaign body must contain 1..4000 characters")
    return {"title": title, "body": body}


def _segment_query(segment: dict[str, Any]):
    stmt = select(User)
    if segment.get("active_only", True):
        stmt = stmt.where(User.is_active.is_(True))
    user_ids = segment.get("user_ids")
    if user_ids:
        stmt = stmt.where(User.id.in_([uuid.UUID(value) for value in user_ids]))
    language_codes = segment.get("language_codes")
    if language_codes:
        stmt = stmt.where(User.language_code.in_(language_codes))
    return stmt


class AdminNotificationService:
    @staticmethod
    async def preview_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        segment: dict[str, Any] | None,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "notifications.read")
        clean_segment = validate_campaign_segment(segment)
        clean_message = validate_campaign_message(message)
        query = _segment_query(clean_segment).subquery()
        recipients = int((await session.scalar(select(func.count()).select_from(query))) or 0)
        return {
            "segment": clean_segment,
            "message": clean_message,
            "recipient_count": recipients,
        }

    @staticmethod
    async def list_campaigns(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        limit: int = 100,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "notifications.read")
        rows = list(
            (
                await session.scalars(
                    select(NotificationCampaign)
                    .order_by(NotificationCampaign.created_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {"items": [AdminNotificationService._campaign_view(item) for item in rows]}

    @staticmethod
    async def get_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        campaign_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "notifications.read")
        item = await session.get(NotificationCampaign, campaign_id)
        if item is None:
            raise LookupError("Campaign not found")
        counts = (
            await session.execute(
                select(NotificationCampaignDelivery.status, func.count(NotificationCampaignDelivery.id))
                .where(NotificationCampaignDelivery.campaign_id == campaign_id)
                .group_by(NotificationCampaignDelivery.status)
            )
        ).all()
        result = AdminNotificationService._campaign_view(item)
        result["deliveries"] = {status: int(count) for status, count in counts}
        return result

    @staticmethod
    def _campaign_view(item: NotificationCampaign) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "name": item.name,
            "status": item.status,
            "channel": item.channel,
            "segment": item.segment,
            "message": item.message,
            "created_by_admin_id": str(item.created_by_admin_id),
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def create_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        name: str,
        segment: dict[str, Any] | None,
        message: dict[str, Any],
        idempotency_key: str,
        request_id: str,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "campaigns.create", confirmed=True)
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 255:
            raise CampaignValidationError("Campaign name must contain 1..255 characters")
        clean_segment = validate_campaign_segment(segment)
        clean_message = validate_campaign_message(message)
        payload = {"name": clean_name, "segment": clean_segment, "message": clean_message}

        async def operation() -> dict[str, Any]:
            item = NotificationCampaign(
                name=clean_name,
                status="draft",
                channel="telegram",
                segment=clean_segment,
                message=clean_message,
                created_by_admin_id=admin.id,
            )
            session.add(item)
            await session.flush()
            return AdminNotificationService._campaign_view(item)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="campaigns.create",
            target_id=None,
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def test_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        campaign_id: uuid.UUID,
        test_user_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "campaigns.test", confirmed=confirmed)
        payload = {"test_user_id": str(test_user_id)}

        async def operation() -> dict[str, Any]:
            campaign = await session.get(NotificationCampaign, campaign_id)
            if campaign is None:
                raise LookupError("Campaign not found")
            user = await session.get(User, test_user_id)
            if user is None or not user.is_active:
                raise LookupError("Test recipient not found")
            notification = Notification(
                user_id=user.id,
                kind="admin_campaign_test",
                title=str(campaign.message["title"]),
                body=str(campaign.message["body"]),
            )
            session.add(notification)
            await session.flush()
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel="telegram",
                purpose="campaign_test",
                status="pending",
            )
            session.add(delivery)
            await session.flush()
            return {
                "campaign_id": str(campaign.id),
                "notification_id": str(notification.id),
                "delivery_id": str(delivery.id),
                "status": delivery.status,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="campaigns.test",
            target_id=str(campaign_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def start_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        campaign_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "campaigns.start",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        payload: dict[str, Any] = {}

        async def operation() -> dict[str, Any]:
            campaign = await session.scalar(
                select(NotificationCampaign)
                .where(NotificationCampaign.id == campaign_id)
                .with_for_update()
            )
            if campaign is None:
                raise LookupError("Campaign not found")
            if campaign.status not in {"draft", "ready", "running"}:
                raise ValueError(f"Campaign cannot start from status {campaign.status}")
            users = list((await session.scalars(_segment_query(campaign.segment))).all())
            existing_ids = set(
                (
                    await session.scalars(
                        select(NotificationCampaignDelivery.user_id).where(
                            NotificationCampaignDelivery.campaign_id == campaign.id
                        )
                    )
                ).all()
            )
            created = 0
            for user in users:
                if user.id in existing_ids:
                    continue
                session.add(
                    NotificationCampaignDelivery(
                        campaign_id=campaign.id,
                        user_id=user.id,
                        status="pending",
                    )
                )
                created += 1
            campaign.status = "running"
            campaign.started_by_admin_id = admin.id
            campaign.started_at = campaign.started_at or datetime.now(UTC)
            await session.flush()
            total = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(NotificationCampaignDelivery)
                        .where(NotificationCampaignDelivery.campaign_id == campaign.id)
                    )
                )
                or 0
            )
            return {
                "campaign_id": str(campaign.id),
                "status": campaign.status,
                "created_deliveries": created,
                "total_deliveries": total,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="campaigns.start",
            target_id=str(campaign_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def cancel_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        campaign_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "campaigns.cancel", confirmed=confirmed)

        async def operation() -> dict[str, Any]:
            campaign = await session.scalar(
                select(NotificationCampaign)
                .where(NotificationCampaign.id == campaign_id)
                .with_for_update()
            )
            if campaign is None:
                raise LookupError("Campaign not found")
            if campaign.status in {"completed", "cancelled"}:
                if campaign.status == "completed":
                    raise ValueError("Completed campaign cannot be cancelled")
                return {"campaign_id": str(campaign.id), "status": campaign.status}
            campaign.status = "cancelled"
            campaign.cancelled_at = datetime.now(UTC)
            await session.execute(
                update(NotificationCampaignDelivery)
                .where(
                    NotificationCampaignDelivery.campaign_id == campaign.id,
                    NotificationCampaignDelivery.status.in_(["pending", "retry"]),
                )
                .values(status="cancelled", lease_until=None)
            )
            return {"campaign_id": str(campaign.id), "status": campaign.status}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="campaigns.cancel",
            target_id=str(campaign_id),
            request_payload={},
            operation=operation,
        )
