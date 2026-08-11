import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, ReferralReward


class ReferralService:
    @staticmethod
    async def stats(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Decimal | int]:
        first = await session.scalar(
            select(func.count()).select_from(ReferralRelation).where(
                ReferralRelation.inviter_user_id == user_id
            )
        )
        first_ids = select(ReferralRelation.referred_user_id).where(
            ReferralRelation.inviter_user_id == user_id
        )
        second = await session.scalar(
            select(func.count()).select_from(ReferralRelation).where(
                ReferralRelation.inviter_user_id.in_(first_ids)
            )
        )
        available = await session.scalar(
            select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
                ReferralReward.partner_user_id == user_id,
                ReferralReward.status == "available",
            )
        )
        pending = await session.scalar(
            select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
                ReferralReward.partner_user_id == user_id,
                ReferralReward.status == "pending",
            )
        )
        return {
            "first_line": int(first or 0),
            "second_line": int(second or 0),
            "available": Decimal(available or 0),
            "pending": Decimal(pending or 0),
        }

    @classmethod
    async def accrue_from_payment(
        cls,
        session: AsyncSession,
        *,
        source_user_id: uuid.UUID,
        source_transaction_id: uuid.UUID,
        payment_amount: Decimal,
    ) -> None:
        first_relation = await session.get(ReferralRelation, source_user_id)
        if first_relation is None:
            return

        await cls._create_reward(
            session,
            partner_user_id=first_relation.inviter_user_id,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
            level=1,
            percent=settings.referral_first_percent,
            payment_amount=payment_amount,
        )

        second_relation = await session.get(
            ReferralRelation,
            first_relation.inviter_user_id,
        )
        if second_relation is None:
            return

        await cls._create_reward(
            session,
            partner_user_id=second_relation.inviter_user_id,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
            level=2,
            percent=settings.referral_second_percent,
            payment_amount=payment_amount,
        )

    @staticmethod
    async def _create_reward(
        session: AsyncSession,
        *,
        partner_user_id: uuid.UUID,
        source_user_id: uuid.UUID,
        source_transaction_id: uuid.UUID,
        level: int,
        percent: Decimal,
        payment_amount: Decimal,
    ) -> None:
        existing = await session.scalar(
            select(ReferralReward).where(
                ReferralReward.partner_user_id == partner_user_id,
                ReferralReward.source_transaction_id == source_transaction_id,
                ReferralReward.level == level,
            )
        )
        if existing is not None:
            return

        amount = (payment_amount * percent / Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        if amount <= 0:
            return
        session.add(
            ReferralReward(
                partner_user_id=partner_user_id,
                source_user_id=source_user_id,
                source_transaction_id=source_transaction_id,
                level=level,
                percent=percent,
                amount=amount,
                status="available",
            )
        )
        await session.flush()
