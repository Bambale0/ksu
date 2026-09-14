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
    credited only after the provider confirms successful payment. Product promo
    bonuses are intentionally limited to packages with at least 1000 base ROX.
    """

    RESERVATION_TTL = timedelta(days=7)
    MIN_PROMO_BASE_CREDITS = Decimal("1000")

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
        package_id: str | None = None,
        base_credits: Decimal | None = None,
    ) -> PromoCode:
        normalized = cls.normalize(code)
        promo = await session.scalar(select(PromoCode).where(PromoCode.code == normalized))
        await cls._validate_available(
            session,
            promo=promo,
            user_id=user_id,
            package_id=package_id,
            base_credits=base_credits,
            allow_pending_reservation=False,
        )
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
        payload = payment.payload or {}
        payment_package_id = str(payload.get("package_id") or "").strip() or None
        base_credits = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        await cls._validate_available(
            session,
            promo=promo,
            user_id=payment.user_id,
            package_id=payment_package_id,
            base_credits=base_credits,
            allow_pending_reservation=True,
        )
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
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="unavailable",
                reason="campaign_missing",
            )
            return Decimal("0")

        now = datetime.now(UTC)
        if redemption.reserved_until is None or redemption.reserved_until <= now:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="reservation_expired",
                reason="reservation_expired",
            )
            return Decimal("0")
        if not promo.is_active:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="inactive",
                reason="campaign_inactive",
            )
            return Decimal("0")
        if promo.expires_at is not None and promo.expires_at <= now:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="expired",
                reason="campaign_expired",
            )
            return Decimal("0")

        payment_package_id = str(payload.get("package_id") or "").strip() or None
        if promo.package_id is not None and promo.package_id != payment_package_id:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="package_mismatch",
                reason="package_mismatch",
            )
            return Decimal("0")

        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        if base < cls.MIN_PROMO_BASE_CREDITS:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="minimum_package_required",
                reason="minimum_package_required",
            )
            return Decimal("0")

        if reward <= 0:
            reward = Decimal(promo.reward_amount)
        if reward <= 0:
            cls._release_bonus(
                payment=payment,
                redemption=redemption,
                status="unavailable",
                reason="invalid_reward",
            )
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
        payload = payment.payload or {}
        if not payload.get("promo_code") and not payload.get("promo_id"):
            return
        redemption = await session.scalar(
            select(PromoRedemption)
            .where(PromoRedemption.payment_id == payment.id)
            .with_for_update()
        )
        if redemption is None or redemption.status != "pending":
            return
        cls._release_bonus(
            payment=payment,
            redemption=redemption,
            status="released",
            reason=reason,
        )

    @staticmethod
    def _release_bonus(
        *,
        payment: Payment,
        redemption: PromoRedemption,
        status: str,
        reason: str | None = None,
    ) -> None:
        payload = payment.payload or {}
        base_credits = str(payload.get("base_credits") or payment.rox_amount)
        package_bonus = Decimal(str(payload.get("package_bonus_credits") or "0"))
        base_total = Decimal(base_credits) + package_bonus
        redemption.status = "released"
        redemption.reserved_until = None
        redemption.redeemed_at = None
        updates: dict[str, object] = {
            "promo_bonus_status": status,
            "bonus_credits": str(package_bonus),
            "credited_credits": str(base_total),
        }
        if reason:
            updates["promo_release_reason"] = reason[:64]
        payment.payload = {**payload, **updates}

    @classmethod
    async def _validate_available(
        cls,
        session: AsyncSession,
        *,
        promo: PromoCode | None,
        user_id: uuid.UUID,
        package_id: str | None,
        base_credits: Decimal | None,
        allow_pending_reservation: bool,
    ) -> None:
        if promo is None or not promo.is_active:
            raise PromoCodeError("invalid", "Promo code is invalid")
        now = datetime.now(UTC)
        if promo.expires_at and promo.expires_at <= now:
            raise PromoCodeError("expired", "Promo code has expired")
        if promo.package_id is not None and package_id is not None and promo.package_id != package_id:
            raise PromoCodeError("package_mismatch", "Promo code is not valid for this package")
        if base_credits is not None and base_credits < cls.MIN_PROMO_BASE_CREDITS:
            raise PromoCodeError(
                "minimum_package_required",
                "Promo code requires a package from 1000 ROX",
            )

        existing = await session.scalar(
            select(PromoRedemption).where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
        if existing is not None and existing.status == "applied":
            raise PromoCodeError("already_used", "Promo code already used")

        has_live_reservation = (
            existing is not None
            and existing.status == "pending"
            and existing.reserved_until is not None
            and existing.reserved_until > now
        )
        if has_live_reservation and not allow_pending_reservation:
            raise PromoCodeError(
                "already_reserved",
                "Promo code is already reserved for another payment",
            )

        await cls._check_capacity(
            session,
            promo=promo,
            now=now,
            exclude_redemption_id=(
                existing.id if has_live_reservation and allow_pending_reservation else None
            ),
        )

    @staticmethod
    async def remaining_uses(
        session: AsyncSession,
        *,
        promo: PromoCode,
    ) -> int | None:
        if promo.max_uses is None:
            return None
        now = datetime.now(UTC)
        pending = int(
            (
                await session.scalar(
                    select(func.count(PromoRedemption.id)).where(
                        PromoRedemption.promo_id == promo.id,
                        PromoRedemption.status == "pending",
                        PromoRedemption.reserved_until > now,
                    )
                )
            )
            or 0
        )
        return max(0, promo.max_uses - promo.uses_count - pending)

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
        package_bonus = Decimal(str(payload.get("package_bonus_credits") or "0"))
        reward = Decimal(promo.reward_amount)
        payment.payload = {
            **payload,
            "base_credits": str(base),
            "promo_id": str(promo.id),
            "promo_code": promo.code,
            "promo_package_id": promo.package_id,
            "promo_reward_credits": str(reward),
            "promo_bonus_status": "reserved",
            "bonus_credits": str(package_bonus + reward),
            "credited_credits": str(base + package_bonus + reward),
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
