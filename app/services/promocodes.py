from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PartnerPromoProgramConfig,
    Payment,
    PromoCode,
    PromoRedemption,
    ReferralRelation,
    User,
)
from app.services.partner_promo_program import PartnerPromoProgramService
from app.services.referral_antifraud import ReferralAntifraudService
from app.services.wallet import WalletService


class PromoCodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PromoActivation:
    promo: PromoCode
    config: PartnerPromoProgramConfig
    activated: bool


class PromoCodeService:
    """Partner promo activation.

    A partner-owned promo activates immutable partner attribution for a user.
    The welcome ROX gift is granted once on activation. Future paid top-ups are
    handled by ReferralService; promo codes never increase a payment package.
    """

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
        promo = await cls._load_valid_promo(session, code=code)
        if promo.partner_user_id == user_id:
            raise PromoCodeError("self_ref", "A partner cannot activate their own promo code")
        partner = await session.get(User, promo.partner_user_id)
        if partner is None or not partner.is_active:
            raise PromoCodeError("partner_unavailable", "Promo partner is unavailable")

        relation = await session.get(ReferralRelation, user_id)
        if (
            relation is not None
            and relation.source == "promo"
            and relation.inviter_user_id != promo.partner_user_id
        ):
            raise PromoCodeError(
                "already_attributed",
                "User is already attributed to another promo partner",
            )
        if not (
            relation is not None
            and relation.source == "promo"
            and relation.inviter_user_id == promo.partner_user_id
        ):
            cls._check_capacity(promo)
        return promo

    @classmethod
    async def activate(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        code: str,
    ) -> PromoActivation:
        config = await PartnerPromoProgramService.get_config(session)
        if not config.is_active:
            raise PromoCodeError("program_inactive", "Partner promo program is inactive")

        user = await session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None or not user.is_active:
            raise PromoCodeError("invalid_user", "User is unavailable")

        normalized = cls.normalize(code)
        promo = await session.scalar(
            select(PromoCode).where(PromoCode.code == normalized).with_for_update()
        )
        cls._validate_promo(promo)
        assert promo is not None and promo.partner_user_id is not None

        if promo.partner_user_id == user_id:
            raise PromoCodeError("self_ref", "A partner cannot activate their own promo code")

        partner = await session.get(User, promo.partner_user_id)
        if partner is None or not partner.is_active:
            raise PromoCodeError("partner_unavailable", "Promo partner is unavailable")

        relation = await session.scalar(
            select(ReferralRelation)
            .where(ReferralRelation.referred_user_id == user_id)
            .with_for_update()
        )
        if (
            relation is not None
            and relation.source == "promo"
            and relation.inviter_user_id != promo.partner_user_id
        ):
            raise PromoCodeError(
                "already_attributed",
                "User is already attributed to another promo partner",
            )

        existing_redemption = await session.scalar(
            select(PromoRedemption)
            .where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
            .with_for_update()
        )

        if (
            relation is not None
            and relation.source == "promo"
            and relation.inviter_user_id == promo.partner_user_id
        ):
            return PromoActivation(promo=promo, config=config, activated=False)

        cls._check_capacity(promo)

        admission = await ReferralAntifraudService.attach_promo_user(
            session,
            visitor=user,
            inviter_user_id=promo.partner_user_id,
            promo_id=promo.id,
        )
        if not admission.attached:
            code = (
                "already_attributed"
                if admission.reason == "already_attributed"
                else f"referral_{admission.reason}"
            )
            raise PromoCodeError(
                code,
                f"Partner referral admission rejected: {admission.reason}",
            )

        now = datetime.now(UTC)
        if existing_redemption is None:
            session.add(
                PromoRedemption(
                    promo_id=promo.id,
                    user_id=user_id,
                    payment_id=None,
                    status="applied",
                    reserved_until=None,
                    redeemed_at=now,
                )
            )
            promo.uses_count += 1
        elif existing_redemption.status != "applied":
            existing_redemption.status = "applied"
            existing_redemption.reserved_until = None
            existing_redemption.redeemed_at = now
            promo.uses_count += 1
        else:
            # Legacy successful-payment promo rows already consumed a campaign
            # use. Keep that accounting, but allow the new attribution to activate.
            existing_redemption.reserved_until = None
            existing_redemption.redeemed_at = now

        if Decimal(config.welcome_rox) > 0:
            await WalletService.credit(
                session,
                user_id=user_id,
                amount=Decimal(config.welcome_rox),
                kind="partner_promo_welcome",
                reference_type="promo",
                reference_id=str(promo.id),
                idempotency_key=f"partner-promo-welcome:{user_id}",
                reason="promo_activation_welcome",
                promo_code=promo.code,
                partner_id=promo.partner_user_id,
                referral_user_id=user_id,
                payment_id=None,
            )

        await session.flush()
        return PromoActivation(promo=promo, config=config, activated=True)

    @classmethod
    async def reserve_for_payment(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        code: str | None,
    ) -> PromoCode | None:
        """Compatibility path for checkout clients that still submit promo_code.

        Activation is immediate and independent from payment success; no ROX are
        reserved for or added to the payment package.
        """
        normalized = cls.normalize(code)
        if not normalized:
            return None

        activation = await cls.activate(
            session,
            user_id=payment.user_id,
            code=normalized,
        )
        cls._attach_payment_metadata(payment, activation.promo)
        await session.flush()
        return activation.promo

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
        """Legacy payment hook: partner promos never add ROX to paid packages."""
        _ = session
        payload = payment.payload or {}
        if payload.get("promo_code"):
            base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
            payment.payload = {
                **payload,
                "promo_bonus_status": "activated",
                "promo_reward_credits": "0",
                "bonus_credits": "0",
                "credited_credits": str(base),
            }
        return Decimal("0")

    @classmethod
    async def release_payment_reservation(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
        reason: str,
    ) -> None:
        """No-op kept for provider failure paths from the former payment promo."""
        _ = (session, payment, reason)

    @classmethod
    async def remaining_uses(
        cls,
        session: AsyncSession,
        *,
        promo: PromoCode,
    ) -> int | None:
        _ = session
        if promo.max_uses is None:
            return None
        return max(0, promo.max_uses - promo.uses_count)

    @classmethod
    async def relation_for_user(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> ReferralRelation | None:
        return await session.get(ReferralRelation, user_id)

    @classmethod
    async def program_config(
        cls,
        session: AsyncSession,
    ) -> PartnerPromoProgramConfig:
        return await PartnerPromoProgramService.get_config(session)

    @classmethod
    async def redeem(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        code: str,
    ) -> PromoCode:
        activation = await cls.activate(session, user_id=user_id, code=code)
        return activation.promo

    @classmethod
    async def _load_valid_promo(
        cls,
        session: AsyncSession,
        *,
        code: str,
    ) -> PromoCode:
        config = await PartnerPromoProgramService.get_config(session)
        if not config.is_active:
            raise PromoCodeError("program_inactive", "Partner promo program is inactive")
        normalized = cls.normalize(code)
        promo = await session.scalar(select(PromoCode).where(PromoCode.code == normalized))
        cls._validate_promo(promo)
        assert promo is not None
        return promo

    @staticmethod
    def _validate_promo(promo: PromoCode | None) -> None:
        if promo is None or not promo.is_active:
            raise PromoCodeError("invalid", "Promo code is invalid")
        if promo.partner_user_id is None:
            raise PromoCodeError("partner_unassigned", "Promo code has no partner")
        now = datetime.now(UTC)
        if promo.expires_at is not None and promo.expires_at <= now:
            raise PromoCodeError("expired", "Promo code has expired")

    @staticmethod
    def _check_capacity(promo: PromoCode) -> None:
        if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
            raise PromoCodeError("usage_limit_reached", "Promo code usage limit reached")

    @staticmethod
    def _attach_payment_metadata(payment: Payment, promo: PromoCode) -> None:
        payload = payment.payload or {}
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        payment.payload = {
            **payload,
            "base_credits": str(base),
            "promo_id": str(promo.id),
            "promo_code": promo.code,
            "promo_partner_user_id": str(promo.partner_user_id),
            "promo_reward_credits": "0",
            "promo_bonus_status": "activated",
            "bonus_credits": "0",
            "credited_credits": str(base),
        }
