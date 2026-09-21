from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, User
from app.db.referral_models import ReferralEvent
from app.services.notifications import NotificationService
from app.services.referral_audit import log_referral_admission
from app.services.referral_notification_copy import referral_joined_copy


@dataclass(frozen=True, slots=True)
class ReferralAdmissionResult:
    attached: bool
    reason: str
    inviter_user_id: uuid.UUID | None = None


class ReferralAntifraudService:
    """Serialize referral admission and apply production anti-fraud limits."""

    @staticmethod
    async def _record(
        session: AsyncSession,
        *,
        visitor: User,
        inviter: User | None,
        inviter_telegram_id: int | None,
        reason: str,
        attached: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> ReferralEvent:
        event = ReferralEvent(
            visitor_user_id=visitor.id,
            visitor_telegram_id=visitor.telegram_id,
            inviter_user_id=inviter.id if inviter is not None else None,
            inviter_telegram_id=(
                inviter.telegram_id if inviter is not None else inviter_telegram_id
            ),
            reason=reason,
            attached=attached,
            details=dict(metadata or {}),
        )
        session.add(event)
        await session.flush()
        log_referral_admission(
            visitor_telegram_id=visitor.telegram_id,
            inviter_telegram_id=(
                inviter.telegram_id if inviter is not None else inviter_telegram_id
            ),
            attached=attached,
            reason=reason,
            inviter_user_id=inviter.id if inviter is not None else None,
        )
        return event

    @staticmethod
    async def _count_since(
        session: AsyncSession,
        *,
        inviter_user_id: uuid.UUID,
        since: datetime,
        exclude_referred_user_id: uuid.UUID | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ReferralRelation)
            .where(
                ReferralRelation.inviter_user_id == inviter_user_id,
                ReferralRelation.created_at >= since,
            )
        )
        if exclude_referred_user_id is not None:
            stmt = stmt.where(ReferralRelation.referred_user_id != exclude_referred_user_id)
        return int((await session.scalar(stmt)) or 0)

    @staticmethod
    async def _would_create_cycle(
        session: AsyncSession,
        *,
        visitor_user_id: uuid.UUID,
        inviter_user_id: uuid.UUID,
    ) -> bool:
        descendants = (
            select(ReferralRelation.referred_user_id.label("user_id"))
            .where(ReferralRelation.inviter_user_id == visitor_user_id)
            .cte("referral_descendants", recursive=True)
        )
        relation = ReferralRelation.__table__
        descendants = descendants.union(
            select(relation.c.referred_user_id).where(
                relation.c.inviter_user_id == descendants.c.user_id
            )
        )
        existing = await session.scalar(
            select(descendants.c.user_id)
            .where(descendants.c.user_id == inviter_user_id)
            .limit(1)
        )
        return existing is not None

    @classmethod
    async def _check_limits(
        cls,
        session: AsyncSession,
        *,
        visitor: User,
        inviter: User,
        exclude_referred_user_id: uuid.UUID | None = None,
    ) -> tuple[ReferralAdmissionResult | None, int, int]:
        now = datetime.now(timezone.utc)
        hourly_limit = max(0, int(settings.referral_antifraud_max_per_hour))
        daily_limit = max(0, int(settings.referral_antifraud_max_per_day))
        burst_max = max(0, int(settings.referral_antifraud_burst_max))
        burst_window = max(0, int(settings.referral_antifraud_burst_window_seconds))

        hourly_count = 0
        if hourly_limit:
            hourly_count = await cls._count_since(
                session,
                inviter_user_id=inviter.id,
                since=now - timedelta(hours=1),
                exclude_referred_user_id=exclude_referred_user_id,
            )
            if hourly_count >= hourly_limit:
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter.telegram_id,
                    reason="hourly_limit",
                    metadata={"count": hourly_count, "limit": hourly_limit},
                )
                return ReferralAdmissionResult(False, "hourly_limit", inviter.id), 0, 0

        daily_count = 0
        if daily_limit:
            daily_count = await cls._count_since(
                session,
                inviter_user_id=inviter.id,
                since=now - timedelta(days=1),
                exclude_referred_user_id=exclude_referred_user_id,
            )
            if daily_count >= daily_limit:
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter.telegram_id,
                    reason="daily_limit",
                    metadata={"count": daily_count, "limit": daily_limit},
                )
                return ReferralAdmissionResult(False, "daily_limit", inviter.id), 0, 0

        if burst_max and burst_window:
            burst_count = await cls._count_since(
                session,
                inviter_user_id=inviter.id,
                since=now - timedelta(seconds=burst_window),
                exclude_referred_user_id=exclude_referred_user_id,
            )
            if burst_count >= max(0, burst_max - 1):
                reason = "burst_limit"
                if settings.referral_antifraud_burst_autoban:
                    inviter.is_active = False
                    reason = "burst_autoban"
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter.telegram_id,
                    reason=reason,
                    metadata={
                        "count_before_attempt": burst_count,
                        "threshold": burst_max,
                        "window_seconds": burst_window,
                    },
                )
                return ReferralAdmissionResult(False, reason, inviter.id), 0, 0

        return None, hourly_count, daily_count

    @classmethod
    async def attach_promo_user(
        cls,
        session: AsyncSession,
        *,
        visitor: User,
        inviter_user_id: uuid.UUID,
        promo_id: uuid.UUID,
    ) -> ReferralAdmissionResult:
        if inviter_user_id == visitor.id:
            await cls._record(
                session,
                visitor=visitor,
                inviter=None,
                inviter_telegram_id=visitor.telegram_id,
                reason="self_ref",
            )
            return ReferralAdmissionResult(False, "self_ref")

        inviter = await session.scalar(
            select(User).where(User.id == inviter_user_id).with_for_update()
        )
        if inviter is None:
            await cls._record(
                session,
                visitor=visitor,
                inviter=None,
                inviter_telegram_id=None,
                reason="inviter_not_found",
            )
            return ReferralAdmissionResult(False, "inviter_not_found")
        if not inviter.is_active:
            await cls._record(
                session,
                visitor=visitor,
                inviter=inviter,
                inviter_telegram_id=inviter.telegram_id,
                reason="blocked_referrer",
            )
            return ReferralAdmissionResult(False, "blocked_referrer", inviter.id)

        relation = await session.scalar(
            select(ReferralRelation)
            .where(ReferralRelation.referred_user_id == visitor.id)
            .with_for_update()
        )
        if relation is not None and relation.inviter_user_id != inviter.id:
            return ReferralAdmissionResult(
                False,
                "already_attributed",
                relation.inviter_user_id,
            )

        if await cls._would_create_cycle(
            session,
            visitor_user_id=visitor.id,
            inviter_user_id=inviter.id,
        ):
            await cls._record(
                session,
                visitor=visitor,
                inviter=inviter,
                inviter_telegram_id=inviter.telegram_id,
                reason="referral_cycle",
            )
            return ReferralAdmissionResult(False, "referral_cycle", inviter.id)

        exclude_current = (
            visitor.id
            if relation is not None and relation.inviter_user_id == inviter.id
            else None
        )
        blocked, hourly_count, daily_count = await cls._check_limits(
            session,
            visitor=visitor,
            inviter=inviter,
            exclude_referred_user_id=exclude_current,
        )
        if blocked is not None:
            return blocked

        if relation is None:
            relation = ReferralRelation(
                referred_user_id=visitor.id,
                inviter_user_id=inviter.id,
                source="promo",
                promo_id=promo_id,
            )
            session.add(relation)
        else:
            relation.inviter_user_id = inviter.id
            relation.source = "promo"
            relation.promo_id = promo_id
        await session.flush()

        await cls._record(
            session,
            visitor=visitor,
            inviter=inviter,
            inviter_telegram_id=inviter.telegram_id,
            reason="promo_attached",
            attached=True,
            metadata={
                "hourly_count_before": hourly_count,
                "daily_count_before": daily_count,
                "promo_id": str(promo_id),
            },
        )
        return ReferralAdmissionResult(True, "promo_attached", inviter.id)

    @classmethod
    async def attach_new_user(
        cls,
        session: AsyncSession,
        *,
        visitor: User,
        inviter_telegram_id: int | None,
    ) -> ReferralAdmissionResult:
        if not inviter_telegram_id:
            return ReferralAdmissionResult(False, "no_referral")

        # Referral ownership is immutable. Existing users may attach on their
        # first Telegram-signed referral launch, but a relation already present
        # for this user must never be replaced by a later share link.
        existing_relation = await session.get(ReferralRelation, visitor.id)
        if existing_relation is not None:
            return ReferralAdmissionResult(
                False,
                "already_attributed",
                existing_relation.inviter_user_id,
            )

        if inviter_telegram_id == visitor.telegram_id:
            await cls._record(
                session,
                visitor=visitor,
                inviter=None,
                inviter_telegram_id=inviter_telegram_id,
                reason="self_ref",
            )
            return ReferralAdmissionResult(False, "self_ref")

        inviter = await session.scalar(
            select(User)
            .where(User.telegram_id == inviter_telegram_id)
            .with_for_update()
        )
        if inviter is None:
            await cls._record(
                session,
                visitor=visitor,
                inviter=None,
                inviter_telegram_id=inviter_telegram_id,
                reason="inviter_not_found",
            )
            return ReferralAdmissionResult(False, "inviter_not_found")

        if not inviter.is_active:
            await cls._record(
                session,
                visitor=visitor,
                inviter=inviter,
                inviter_telegram_id=inviter_telegram_id,
                reason="blocked_referrer",
            )
            return ReferralAdmissionResult(False, "blocked_referrer", inviter.id)

        # Same-inviter cold-boot requests serialize on this row. Re-check after
        # acquiring the lock so only the first one runs admission/accounting.
        existing_relation = await session.get(ReferralRelation, visitor.id)
        if existing_relation is not None:
            return ReferralAdmissionResult(
                False,
                "already_attributed",
                existing_relation.inviter_user_id,
            )

        blocked, hourly_count, daily_count = await cls._check_limits(
            session,
            visitor=visitor,
            inviter=inviter,
        )
        if blocked is not None:
            return blocked

        attached_user_id = (
            await session.execute(
                insert(ReferralRelation)
                .values(
                    referred_user_id=visitor.id,
                    inviter_user_id=inviter.id,
                )
                .on_conflict_do_nothing(index_elements=[ReferralRelation.referred_user_id])
                .returning(ReferralRelation.referred_user_id)
            )
        ).scalar_one_or_none()
        if attached_user_id is None:
            # A different inviter may have won a concurrent first-attribution
            # race. Keep the first relation and do not award this inviter.
            relation = await session.get(ReferralRelation, visitor.id)
            return ReferralAdmissionResult(
                False,
                "already_attributed",
                relation.inviter_user_id if relation is not None else None,
            )
        await session.flush()

        notification_copy = referral_joined_copy(
            username=visitor.username,
            first_name=visitor.first_name,
            last_name=visitor.last_name,
        )
        await NotificationService.create(
            session,
            user_id=inviter.id,
            kind="referral_joined",
            title=notification_copy.title,
            body=notification_copy.body,
        )

        await cls._record(
            session,
            visitor=visitor,
            inviter=inviter,
            inviter_telegram_id=inviter_telegram_id,
            reason="attached",
            attached=True,
            metadata={
                "hourly_count_before": hourly_count,
                "daily_count_before": daily_count,
            },
        )
        return ReferralAdmissionResult(True, "attached", inviter.id)
