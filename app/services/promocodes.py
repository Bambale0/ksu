from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PromoCode, PromoRedemption
from app.services.wallet import WalletService


class PromoCodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PromoCodeService:
    """Paid top-up promo codes.

    A promo code reserves a fixed ROX gift for a payment intent. The gift is
    credited only after the provider confirms successful payment.
    """

    RESERVATION_TTL = timedelta(days=7)

    @staticmethod
    def normalize(code: str | None) -> str:
        return str(code or "").strip().upper()

    @classmethod
    async def preview(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        code: str,
    ) -> PromoCode:
        normalized = cls.normalize(code)
        promo = await session.scalar(select(PromoCode).where(PromoCode.code == normalized))
        await cls._validate_available(session, promo=promo, user_id=user_id)
        assert promo is not None
        return promo

    @classmethod
    async def reserve_for_payment(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        code: str | None,
    ) -> PromoCode | None:
        normalized = cls.normalize(code)
        if not normalized:
            return None

        promo = await session.scalar(
            select(PromoCode).where(PromoCode.code == normalized).with_for_update()
        )
        await cls._validate_available(session, promo=promo, user_id=payment.user_id)
        assert promo is not None

        now = datetime.now(UTC)
        existing = await session.scalar(
            select(PromoRedemption)
            .where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == payment.user_id,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.status == "applied":
                raise PromoCodeError("already_used", "Promo code already used")
            if (
                existing.status == "pending"
                and existing.reserved_until is not None
                and existing.reserved_until > now
            ):
                if existing.payment_id == payment.id:
                    cls._attach_payload(payment, promo)
                    return promo
                raise PromoCodeError(
                    "already_reserved",
                    "Promo code is already reserved for another payment",
                )

        await cls._check_capacity(
            session,
            promo=promo,
            now=now,
            exclude_redemption_id=existing.id if existing is not None else None,
        )

        if existing is None:
            existing = PromoRedemption(
                promo_id=promo.id,
                user_id=payment.user_id,
                payment_id=payment.id,
                status="pending",
                reserved_until=now + cls.RESERVATION_TTL,
            )
            session.add(existing)
        else:
            existing.payment_id = payment.id
            existing.status = "pending"
            existing.reserved_until = now + cls.RESERVATION_TTL
            existing.redeemed_at = None

        cls._attach_payload(payment, promo)
        await session.flush()
        return promo

    @classmethod
    def assert_payment_code(cls, payment: Payment, requested_code: str | None) -> None:
        actual = cls.normalize((payment.payload or {}).get("promo_code"))
        requested = cls.normalize(requested_code)
        if actual != requested:
            from app.services.payment_creation import PaymentIdempotencyConflict

            raise PaymentIdempotencyConflict(
                "The idempotency key was already used for another payment intent"
            )

    @classmethod
    async def apply_payment_bonus(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
    ) -> Decimal:
        redemption = await session.scalar(
            select(PromoRedemption)
            .where(PromoRedemption.payment_id == payment.id)
            .with_for_update()
        )
        if redemption is None:
            return Decimal("0")

        payload = payment.payload or {}
        reward = Decimal(str(payload.get("promo_reward_credits") or "0"))
        if redemption.status == "applied":
            return reward
        if redemption.status != "pending":
            return Decimal("0")

        promo = await session.scalar(
            select(PromoCode).where(PromoCode.id == redemption.promo_id).with_for_update()
        )
        if promo is None:
            redemption.status = "released"
            redemption.reserved_until = None
            payment.payload = {**payload, "promo_bonus_status": "unavailable"}
            return Decimal("0")

        now = datetime.now(UTC)
        if (
            redemption.reserved_until is not None
            and redemption.reserved_until <= now
            and promo.max_uses is not None
            and promo.uses_count >= promo.max_uses
        ):
            redemption.status = "released"
            redemption.reserved_until = None
            payment.payload = {**payload, "promo_bonus_status": "limit_reached"}
            return Decimal("0")

        if reward <= 0:
            reward = Decimal(promo.reward_amount)
        if reward <= 0:
            redemption.status = "released"
            redemption.reserved_until = None
            payment.payload = {**payload, "promo_bonus_status": "unavailable"}
            return Decimal("0")

        await WalletService.credit(
            session,
            user_id=payment.user_id,
            amount=reward,
            kind="promo_bonus",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment:{payment.id}:promo_bonus",
        )
        promo.uses_count += 1
        redemption.status = "applied"
        redemption.reserved_until = None
        redemption.redeemed_at = now
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        payment.payload = {
            **payload,
            "promo_bonus_status": "applied",
            "bonus_credits": str(reward),
            "credited_credits": str(base + reward),
        }
        return reward

    @classmethod
    async def release_payment_reservation(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        reason: str,
    ) -> None:
        redemption = await session.scalar(
            select(PromoRedemption)
            .where(PromoRedemption.payment_id == payment.id)
            .with_for_update()
        )
        if redemption is None or redemption.status != "pending":
            return
        redemption.status = "released"
        redemption.reserved_until = None
        payment.payload = {
            **(payment.payload or {}),
            "promo_bonus_status": "released",
            "promo_release_reason": reason[:64],
        }

    @classmethod
    async def _validate_available(
        cls,
        session: AsyncSession,
        *,
        promo: PromoCode | None,
        user_id: uuid.UUID,
    ) -> None:
        if promo is None or not promo.is_active:
            raise PromoCodeError("invalid", "Promo code is invalid")
        now = datetime.now(UTC)
        if promo.expires_at and promo.expires_at <= now:
            raise PromoCodeError("expired", "Promo code has expired")

        existing = await session.scalar(
            select(PromoRedemption).where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
        if existing is not None and existing.status == "applied":
            raise PromoCodeError("already_used", "Promo code already used")
        await cls._check_capacity(
            session,
            promo=promo,
            now=now,
            exclude_redemption_id=(
                existing.id
                if existing is not None
                and existing.status == "pending"
                and existing.reserved_until is not None
                and existing.reserved_until > now
                else None
            ),
        )

    @staticmethod
    async def _check_capacity(
        session: AsyncSession,
        *,
        promo: PromoCode,
        now: datetime,
        exclude_redemption_id: uuid.UUID | None,
    ) -> None:
        if promo.max_uses is None:
            return
        query = select(func.count(PromoRedemption.id)).where(
            PromoRedemption.promo_id == promo.id,
            PromoRedemption.status == "pending",
            PromoRedemption.reserved_until > now,
        )
        if exclude_redemption_id is not None:
            query = query.where(PromoRedemption.id != exclude_redemption_id)
        pending = int((await session.scalar(query)) or 0)
        if promo.uses_count + pending >= promo.max_uses:
            raise PromoCodeError("usage_limit_reached", "Promo code usage limit reached")

    @staticmethod
    def _attach_payload(payment: Payment, promo: PromoCode) -> None:
        payload = payment.payload or {}
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        reward = Decimal(promo.reward_amount)
        payment.payload = {
            **payload,
            "base_credits": str(base),
            "promo_id": str(promo.id),
            "promo_code": promo.code,
            "promo_reward_credits": str(reward),
            "promo_bonus_status": "reserved",
            "bonus_credits": str(reward),
            "credited_credits": str(base + reward),
        }

    @classmethod
    async def redeem(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        code: str,
    ) -> PromoCode:
        """Compatibility alias: validate only; never grants free ROX."""
        return await cls.preview(session, user_id=user_id, code=code)
