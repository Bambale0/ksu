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
from app.db.partner_wallet_models import PartnerWalletTransfer, PartnerWithdrawalRequest
from app.db.payment_models import ReferralRewardReversal
from app.services.feed_links import bot_start_link, mini_app_deep_link, profile_payload, referral_payload


class PartnerWithdrawalError(ValueError):
    pass


class PartnerInsufficientFunds(PartnerWithdrawalError):
    pass


class PartnerWithdrawalBelowMinimum(PartnerWithdrawalError):
    pass


class PartnerWithdrawalIdempotencyConflict(PartnerWithdrawalError):
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
        transferred = Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PartnerWalletTransfer.amount_rub), 0)).where(
                        PartnerWalletTransfer.user_id == user_id
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
        spent = reserved + transferred
        return {
            "total_earned": net_earned,
            "available": max(Decimal("0"), net_earned - spent),
            "pending_rewards": pending_rewards,
            "pending_withdrawals": pending_withdrawals,
            "reserved_or_paid": reserved,
            "transferred_to_rox": transferred,
        }

    @staticmethod
    async def _withdrawal_replay(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        key: str,
        amount: Decimal,
        requisites: str,
    ) -> PartnerWithdrawal | None:
        request = await session.scalar(
            select(PartnerWithdrawalRequest).where(
                PartnerWithdrawalRequest.user_id == user_id,
                PartnerWithdrawalRequest.idempotency_key == key,
            )
        )
        if request is None:
            return None
        if Decimal(request.amount_rub) != amount or request.requisites != requisites:
            raise PartnerWithdrawalIdempotencyConflict(
                "Idempotency key was already used for another withdrawal intent"
            )
        withdrawal = await session.get(PartnerWithdrawal, request.withdrawal_id)
        if withdrawal is None:
            raise RuntimeError("Idempotent withdrawal request is inconsistent")
        return withdrawal

    @classmethod
    async def create_withdrawal(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        requisites: str,
        idempotency_key: str,
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
        key = idempotency_key.strip()
        if not key or len(key) > 160:
            raise PartnerWithdrawalError("Valid Idempotency-Key is required")

        replay = await cls._withdrawal_replay(
            session,
            user_id=user_id,
            key=key,
            amount=amount,
            requisites=cleaned,
        )
        if replay is not None:
            return replay

        # Serialize all partner-money admission for one user. This lock is shared
        # with RUB->ROX conversion, so concurrent cash/credit spending cannot consume
        # the same earnings twice. The replay is re-checked under that lock.
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise LookupError("User not found")
        replay = await cls._withdrawal_replay(
            session,
            user_id=user_id,
            key=key,
            amount=amount,
            requisites=cleaned,
        )
        if replay is not None:
            return replay

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
        session.add(
            PartnerWithdrawalRequest(
                user_id=user_id,
                withdrawal_id=withdrawal.id,
                idempotency_key=key,
                amount_rub=amount,
                requisites=cleaned,
            )
        )
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

        payload = referral_payload(telegram_id)
        return mini_app_deep_link(payload, fallback_url=bot_start_link(payload))

    @staticmethod
    def referral_mini_app_link(telegram_id: int) -> str | None:
        """Secondary Mini App URL kept for diagnostics and BotFather setups that support it."""

        payload = referral_payload(telegram_id)
        return mini_app_deep_link(payload, fallback_url=bot_start_link(payload))

    @staticmethod
    def profile_link(telegram_id: int) -> str | None:
        """Public author profile link with referral attribution preserved."""

        payload = profile_payload(telegram_id)
        return mini_app_deep_link(payload, fallback_url=bot_start_link(payload))
