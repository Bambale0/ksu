from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.models import (
    PartnerWithdrawal,
    ReferralRelation,
    ReferralReward,
    User,
)
from app.db.payment_models import ReferralRewardReversal
from app.services.feed_links import mini_app_deep_link, referral_payload


class PartnerWithdrawalError(ValueError):
    pass


class PartnerInsufficientFunds(PartnerWithdrawalError):
    pass


class PartnerWithdrawalBelowMinimum(PartnerWithdrawalError):
    pass


class PartnerService:
    RESERVED_WITHDRAWAL_STATUSES = ("pending", "processing", "paid")

    @staticmethod
    async def _reward_totals(session: AsyncSession, user_id: uuid.UUID) -> tuple[Decimal, Decimal]:
        gross = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
                        ReferralReward.partner_user_id == user_id,
                        ReferralReward.status.in_(("available", "reversed")),
                    )
                )
            )
            or 0
        )
        reversals = Decimal(
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
        return gross, reversals

    @classmethod
    async def accounting(cls, session: AsyncSession, user_id: uuid.UUID) -> dict[str, Decimal]:
        gross, reversals = await cls._reward_totals(session, user_id)
        pending_rewards = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
                        ReferralReward.partner_user_id == user_id,
                        ReferralReward.status == "pending",
                    )
                )
            )
            or 0
        )
        reserved = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PartnerWithdrawal.amount), 0)).where(
                        PartnerWithdrawal.user_id == user_id,
                        PartnerWithdrawal.status.in_(cls.RESERVED_WITHDRAWAL_STATUSES),
                    )
                )
            )
            or 0
        )
        pending_withdrawals = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PartnerWithdrawal.amount), 0)).where(
                        PartnerWithdrawal.user_id == user_id,
                        PartnerWithdrawal.status.in_(("pending", "processing")),
                    )
                )
            )
            or 0
        )
        net_earned = max(Decimal("0"), gross - reversals)
        return {
            "total_earned": net_earned,
            "available": max(Decimal("0"), net_earned - reserved),
            "pending_rewards": pending_rewards,
            "pending_withdrawals": pending_withdrawals,
            "reserved_or_paid": reserved,
        }

    @classmethod
    async def create_withdrawal(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        requisites: str,
    ) -> PartnerWithdrawal:
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount <= 0:
            raise PartnerWithdrawalError("Withdrawal amount must be positive")
        minimum = max(Decimal("0"), Decimal(settings.partner_min_withdrawal_rub))
        if minimum and amount < minimum:
            raise PartnerWithdrawalBelowMinimum(
                f"Minimum withdrawal is {minimum:.2f} RUB"
            )
        cleaned = requisites.strip()
        if not cleaned:
            raise PartnerWithdrawalError("Withdrawal requisites are required")

        # Serialize withdrawal admission for one partner. The same lock is held while
        # calculating available earnings and inserting the reservation row.
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise LookupError("User not found")
        accounting = await cls.accounting(session, user_id)
        if amount > accounting["available"]:
            raise PartnerInsufficientFunds("Withdrawal amount exceeds available partner balance")

        withdrawal = PartnerWithdrawal(
            user_id=user_id,
            amount=amount,
            status="pending",
            requisites={"details": cleaned},
        )
        session.add(withdrawal)
        await session.flush()
        return withdrawal

    @staticmethod
    async def cancel_withdrawal(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        withdrawal_id: uuid.UUID,
    ) -> PartnerWithdrawal:
        withdrawal = await session.scalar(
            select(PartnerWithdrawal)
            .where(
                PartnerWithdrawal.id == withdrawal_id,
                PartnerWithdrawal.user_id == user_id,
            )
            .with_for_update()
        )
        if withdrawal is None:
            raise LookupError("Withdrawal not found")
        if withdrawal.status != "pending":
            raise PartnerWithdrawalError("Only pending withdrawals can be canceled")
        withdrawal.status = "canceled"
        await session.flush()
        return withdrawal

    @staticmethod
    async def invitation_counts(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
        first = int(
            (
                await session.scalar(
                    select(func.count()).select_from(ReferralRelation).where(
                        ReferralRelation.inviter_user_id == user_id
                    )
                )
            )
            or 0
        )
        first_ids = select(ReferralRelation.referred_user_id).where(
            ReferralRelation.inviter_user_id == user_id
        )
        second = int(
            (
                await session.scalar(
                    select(func.count()).select_from(ReferralRelation).where(
                        ReferralRelation.inviter_user_id.in_(first_ids)
                    )
                )
            )
            or 0
        )
        return first, second

    @staticmethod
    async def invitations(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        line: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        if line in (None, 1):
            first_rows = list(
                (
                    await session.execute(
                        select(ReferralRelation, User)
                        .join(User, User.id == ReferralRelation.referred_user_id)
                        .where(ReferralRelation.inviter_user_id == user_id)
                        .order_by(ReferralRelation.created_at.desc())
                    )
                ).all()
            )
            items.extend(
                {
                    "user_id": str(user.id),
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "line": 1,
                    "joined_at": relation.created_at,
                }
                for relation, user in first_rows
            )

        if line in (None, 2):
            first_relation = aliased(ReferralRelation)
            second_relation = aliased(ReferralRelation)
            second_rows = list(
                (
                    await session.execute(
                        select(second_relation, User)
                        .join(
                            first_relation,
                            first_relation.referred_user_id == second_relation.inviter_user_id,
                        )
                        .join(User, User.id == second_relation.referred_user_id)
                        .where(first_relation.inviter_user_id == user_id)
                        .order_by(second_relation.created_at.desc())
                    )
                ).all()
            )
            items.extend(
                {
                    "user_id": str(user.id),
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "line": 2,
                    "joined_at": relation.created_at,
                }
                for relation, user in second_rows
            )

        items.sort(key=lambda item: item["joined_at"], reverse=True)
        return items[offset : offset + limit]

    @staticmethod
    def referral_link(telegram_id: int) -> str | None:
        """Canonical public referral link: open ROXY Mini App directly."""

        username = settings.bot_username.strip().lstrip("@")
        if not username:
            return None
        payload = referral_payload(telegram_id)
        return mini_app_deep_link(
            payload,
            fallback_url=f"https://t.me/{username}?start={payload}",
        )

    @staticmethod
    def referral_mini_app_link(telegram_id: int) -> str | None:
        """Secondary Mini App URL kept for diagnostics and BotFather setups that support it."""

        return mini_app_deep_link(referral_payload(telegram_id))
