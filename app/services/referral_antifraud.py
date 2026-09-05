from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, User
from app.db.referral_models import ReferralEvent
from app.services.wallet import WalletService


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
        return event

    @staticmethod
    async def _count_since(
        session: AsyncSession,
        *,
        inviter_user_id: uuid.UUID,
        since: datetime,
    ) -> int:
        return int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ReferralRelation)
                    .where(
                        ReferralRelation.inviter_user_id == inviter_user_id,
                        ReferralRelation.created_at >= since,
                    )
                )
            )
            or 0
        )

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
            )
            if hourly_count >= hourly_limit:
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter_telegram_id,
                    reason="hourly_limit",
                    metadata={"count": hourly_count, "limit": hourly_limit},
                )
                return ReferralAdmissionResult(False, "hourly_limit", inviter.id)

        daily_count = 0
        if daily_limit:
            daily_count = await cls._count_since(
                session,
                inviter_user_id=inviter.id,
                since=now - timedelta(days=1),
            )
            if daily_count >= daily_limit:
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter_telegram_id,
                    reason="daily_limit",
                    metadata={"count": daily_count, "limit": daily_limit},
                )
                return ReferralAdmissionResult(False, "daily_limit", inviter.id)

        if burst_max and burst_window:
            burst_count = await cls._count_since(
                session,
                inviter_user_id=inviter.id,
                since=now - timedelta(seconds=burst_window),
            )
            # Match the proven Tanya production semantics: the current attempted
            # referral counts toward the threshold, so attempt N is blocked when
            # N would equal the configured burst maximum.
            if burst_count >= max(0, burst_max - 1):
                reason = "burst_limit"
                if settings.referral_antifraud_burst_autoban:
                    inviter.is_active = False
                    reason = "burst_autoban"
                await cls._record(
                    session,
                    visitor=visitor,
                    inviter=inviter,
                    inviter_telegram_id=inviter_telegram_id,
                    reason=reason,
                    metadata={
                        "count_before_attempt": burst_count,
                        "threshold": burst_max,
                        "window_seconds": burst_window,
                    },
                )
                return ReferralAdmissionResult(False, reason, inviter.id)

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

        if settings.invite_bonus_rox > Decimal("0"):
            await WalletService.credit(
                session,
                user_id=inviter.id,
                amount=settings.invite_bonus_rox,
                kind="referral_invite_bonus",
                reference_type="referral_user",
                reference_id=str(visitor.id),
                idempotency_key=f"invite-bonus:{visitor.id}",
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
