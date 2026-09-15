import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, ReferralRelation, ReferralReward, WalletTransaction
from app.db.payment_models import ReferralRewardReversal
from app.services.partner_promo_program import PartnerPromoProgramService
from app.services.wallet import WalletService


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

    @staticmethod
    async def _source_payment(
        session: AsyncSession,
        *,
        source_user_id: uuid.UUID,
        source_transaction_id: uuid.UUID,
    ) -> Payment | None:
        wallet_tx = await session.get(WalletTransaction, source_transaction_id)
        if (
            wallet_tx is None
            or wallet_tx.user_id != source_user_id
            or wallet_tx.kind != "payment"
            or wallet_tx.reference_type != "payment"
            or not wallet_tx.reference_id
        ):
            return None

        try:
            payment_id = uuid.UUID(str(wallet_tx.reference_id))
        except (TypeError, ValueError, AttributeError):
            return None

        payment = await session.get(Payment, payment_id)
        if payment is None or payment.user_id != source_user_id:
            return None
        return payment

    @classmethod
    async def _paid_rub_basis(
        cls,
        session: AsyncSession,
        *,
        source_user_id: uuid.UUID,
        source_transaction_id: uuid.UUID,
    ) -> Decimal | None:
        """Return the authoritative withdrawable RUB basis for a real paid order."""
        payment = await cls._source_payment(
            session,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
        )
        if payment is None:
            return None

        currency = str(payment.currency or "").strip().upper()
        if currency == "RUB":
            basis = Decimal(payment.amount)
        else:
            payload = payment.payload if isinstance(payment.payload, dict) else {}
            explicit_rub_basis = payload.get("referral_basis_rub")
            if explicit_rub_basis in (None, ""):
                return None
            try:
                basis = Decimal(str(explicit_rub_basis))
            except Exception:
                return None

        basis = basis.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return basis if basis > 0 else None

    @classmethod
    async def accrue_from_payment(
        cls,
        session: AsyncSession,
        *,
        source_user_id: uuid.UUID,
        source_transaction_id: uuid.UUID,
        payment_amount: Decimal | None = None,
    ) -> None:
        relation = await session.get(ReferralRelation, source_user_id)
        if relation is None or relation.source != "promo" or relation.promo_id is None:
            return

        config = await PartnerPromoProgramService.get_config(session)
        if not config.is_active:
            return

        # Validate that the source is a real successful-payment wallet transaction.
        source_payment = await cls._source_payment(
            session,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
        )
        if source_payment is None:
            return

        # Retained only for backwards compatibility with existing provider call
        # sites. Cash commission always comes from the authoritative Payment row.
        _ = payment_amount
        reward_basis = await cls._paid_rub_basis(
            session,
            source_user_id=source_user_id,
            source_transaction_id=source_transaction_id,
        )
        if reward_basis is not None and Decimal(config.first_line_percent) > 0:
            await cls._create_reward(
                session,
                partner_user_id=relation.inviter_user_id,
                source_user_id=source_user_id,
                source_transaction_id=source_transaction_id,
                level=1,
                percent=Decimal(config.first_line_percent),
                payment_amount=reward_basis,
            )

        fixed_rox = Decimal(config.topup_partner_rox)
        if fixed_rox > 0:
            idempotency_key = f"partner-promo-topup:{source_transaction_id}"
            existing = await session.scalar(
                select(WalletTransaction).where(
                    WalletTransaction.idempotency_key == idempotency_key
                )
            )
            if existing is None:
                await WalletService.credit(
                    session,
                    user_id=relation.inviter_user_id,
                    amount=fixed_rox,
                    kind="partner_promo_topup_bonus",
                    reference_type="payment",
                    reference_id=str(source_payment.id),
                    idempotency_key=idempotency_key,
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
        if ratio >= Decimal("1"):
            bonus_key = f"partner-promo-topup:{source_transaction_id}"
            bonus_tx = await session.scalar(
                select(WalletTransaction).where(
                    WalletTransaction.idempotency_key == bonus_key
                )
            )
            if bonus_tx is not None and Decimal(bonus_tx.amount) > 0:
                await WalletService.accounting_debit(
                    session,
                    user_id=bonus_tx.user_id,
                    amount=Decimal(bonus_tx.amount),
                    kind="partner_promo_topup_reversal",
                    reference_type="wallet_transaction",
                    reference_id=str(source_transaction_id),
                    idempotency_key=f"partner-promo-topup-reversal:{source_transaction_id}",
                )

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
