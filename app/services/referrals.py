import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ReferralRelation, ReferralReward, WalletTransaction
from app.db.payment_models import ReferralRewardReversal


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

        available_rewards = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
                        ReferralReward.partner_user_id == user_id,
                        ReferralReward.status.in_(["available", "reversed"]),
                    )
                )
            )
            or 0
        )
        available_reversals = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(ReferralRewardReversal.amount), 0))
                    .select_from(ReferralRewardReversal)
                    .join(ReferralReward, ReferralReward.id == ReferralRewardReversal.reward_id)
                    .where(ReferralReward.partner_user_id == user_id)
                )
            )
            or 0
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
            "available": max(Decimal("0"), available_rewards - available_reversals),
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

        # Referral income is denominated in withdrawable ROX/RUB. For a real
        # successful top-up the wallet payment transaction records exactly how many
        # public ROX were purchased, independent of provider currency. Since
        # 1 ROX = 1 RUB this is the correct reward basis for RUB, USD, EUR and crypto
        # checkouts alike. Fall back to payment_amount only for legacy/direct callers.
        wallet_tx = await session.get(WalletTransaction, source_transaction_id)
        reward_basis = Decimal(payment_amount)
        if (
            wallet_tx is not None
            and wallet_tx.user_id == source_user_id
            and wallet_tx.kind == "payment"
            and Decimal(wallet_tx.amount) > 0
        ):
            reward_basis = Decimal(wallet_tx.amount)

        await cls._create_reward(
            session,
            partner_user_id=first_relation.inviter_user_id,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
            level=1,
            percent=settings.referral_first_percent,
            payment_amount=reward_basis,
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
            payment_amount=reward_basis,
        )

    @staticmethod
    async def reverse_payment_rewards(
        session: AsyncSession,
        *,
        source_transaction_id: uuid.UUID,
        payment_reversal_id: uuid.UUID,
        cumulative_ratio: Decimal,
    ) -> None:
        """Adjust referral earnings to match the cumulative refunded payment share."""

        ratio = min(Decimal("1"), max(Decimal("0"), cumulative_ratio))
        rewards = list(
            (
                await session.scalars(
                    select(ReferralReward)
                    .where(ReferralReward.source_transaction_id == source_transaction_id)
                    .with_for_update()
                )
            ).all()
        )
        for reward in rewards:
            already_reversed = Decimal(
                (
                    await session.scalar(
                        select(func.coalesce(func.sum(ReferralRewardReversal.amount), 0)).where(
                            ReferralRewardReversal.reward_id == reward.id
                        )
                    )
                )
                or 0
            )
            target = (Decimal(reward.amount) * ratio).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            target = min(Decimal(reward.amount), target)
            incremental = target - already_reversed
            if incremental > 0:
                session.add(
                    ReferralRewardReversal(
                        reward_id=reward.id,
                        payment_reversal_id=payment_reversal_id,
                        amount=incremental,
                    )
                )
            reward.status = "reversed" if target >= Decimal(reward.amount) else "available"
        await session.flush()

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
