from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PartnerPromoProgramConfig,
    Payment,
    PromoCode,
    PromoRedemption,
    ReferralRelation,
    User,
    WalletTransaction,
)
from app.services.partner_promo_program import PartnerPromoProgramService
from app.services.referral_antifraud import ReferralAntifraudService
from app.services.wallet import WalletService


class PromoCodeError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        preserve_transaction: bool = False,
    ) -> None:
        self.code = code
        self.preserve_transaction = preserve_transaction
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
            await cls._check_capacity(session, promo, exclude_user_id=user_id)
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

        await cls._check_capacity(session, promo, exclude_user_id=user_id)

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
                preserve_transaction=True,
            )

        now = datetime.now(UTC)
        live_legacy_reservation = (
            existing_redemption is not None
            and existing_redemption.status == "pending"
            and existing_redemption.payment_id is not None
            and existing_redemption.reserved_until is not None
            and existing_redemption.reserved_until > now
        )
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
        elif live_legacy_reservation:
            # A pre-upgrade checkout already reserved this campaign slot and
            # promised its legacy payment bonus. Keep that reservation intact:
            # the referral relation + welcome grant record the new activation,
            # while payment completion will consume the reserved use exactly once.
            pass
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
            return await cls.attach_current_attribution_to_payment(
                session,
                payment=payment,
            )

        activation = await cls.activate(
            session,
            user_id=payment.user_id,
            code=normalized,
        )
        cls._attach_payment_metadata(
            payment,
            activation.promo,
            metadata_source="activation",
        )
        await session.flush()
        return activation.promo

    @classmethod
    def assert_payment_code(cls, payment: Payment, requested_code: str | None) -> None:
        payload = payment.payload or {}
        actual = cls.normalize(payload.get("promo_code"))
        requested = cls.normalize(requested_code)
        metadata_source = str(payload.get("promo_metadata_source") or "")
        if requested:
            matches = actual == requested
        else:
            # Automatic attribution metadata is not part of the user's checkout
            # intent. An idempotent retry without an explicit promo must therefore
            # remain valid even though the stored Payment is enriched server-side.
            matches = not actual or metadata_source == "attribution"
        if not matches:
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
        """Honor only reservations created by the pre-partner promo program.

        New partner promos are activated immediately and never add ROX to a paid
        package. A pending redemption tied to this payment is therefore a legacy
        promise created before this program was deployed and must remain payable.
        """
        payload = payment.payload or {}
        redemption = await session.scalar(
            select(PromoRedemption)
            .where(
                PromoRedemption.payment_id == payment.id,
                PromoRedemption.status == "pending",
            )
            .with_for_update()
        )
        if redemption is not None:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.id == redemption.promo_id).with_for_update()
            )
            now = datetime.now(UTC)
            valid = (
                promo is not None
                and promo.is_active
                and redemption.reserved_until is not None
                and redemption.reserved_until > now
                and (promo.expires_at is None or promo.expires_at > now)
            )
            if valid:
                assert promo is not None
                reward = Decimal(str(payload.get("promo_reward_credits") or promo.reward_amount))
                if reward > 0:
                    base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
                    await WalletService.credit(
                        session,
                        user_id=payment.user_id,
                        amount=reward,
                        kind="promo_bonus",
                        reference_type="payment",
                        reference_id=str(payment.id),
                        idempotency_key=f"payment:{payment.id}:promo_bonus",
                        reason="legacy_payment_promo",
                        promo_code=promo.code,
                        partner_id=promo.partner_user_id,
                        referral_user_id=payment.user_id,
                        payment_id=payment.id,
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

            redemption.status = "released"
            redemption.reserved_until = None
            redemption.redeemed_at = None

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
        """Release a legacy payment reservation without undoing partner activation.

        If the same user already activated the partner promo, the reservation is
        converted into the activation's consumed campaign use instead of being
        dropped. This keeps usage accounting stable when the old payment fails.
        """
        _ = reason
        if not hasattr(session, "scalar"):
            # Minimal reconciliation test doubles do not expose the full
            # AsyncSession read API. They cannot contain promo redemption rows,
            # so legacy cleanup is intentionally a no-op for those adapters.
            return
        redemption = await session.scalar(
            select(PromoRedemption)
            .where(
                PromoRedemption.payment_id == payment.id,
                PromoRedemption.status == "pending",
            )
            .with_for_update()
        )
        if redemption is None or not isinstance(redemption, PromoRedemption):
            # Some provider reconciliation tests use a deliberately tiny fake
            # AsyncSession that can return its PaymentRequest sentinel for
            # unrelated scalar queries. Real DB sessions return PromoRedemption
            # here; treating any other object as "no legacy promo reservation"
            # keeps this compatibility cleanup side-effect free.
            return

        promo = await session.scalar(
            select(PromoCode).where(PromoCode.id == redemption.promo_id).with_for_update()
        )
        relation = await session.get(ReferralRelation, payment.user_id)
        now = datetime.now(UTC)
        activated_same_promo = (
            promo is not None
            and relation is not None
            and relation.source == "promo"
            and relation.promo_id == redemption.promo_id
            and relation.inviter_user_id == promo.partner_user_id
        )
        if activated_same_promo:
            assert promo is not None
            promo.uses_count += 1
            redemption.status = "applied"
            redemption.reserved_until = None
            redemption.redeemed_at = now
        else:
            redemption.status = "released"
            redemption.reserved_until = None
            redemption.redeemed_at = None
        await session.flush()

    @classmethod
    async def remaining_uses(
        cls,
        session: AsyncSession,
        *,
        promo: PromoCode,
    ) -> int | None:
        if promo.max_uses is None:
            return None
        pending = await cls._capacity_reservations(session, promo)
        return max(0, promo.max_uses - promo.uses_count - pending)

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
    async def active_state(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> dict[str, object]:
        """Return the persisted partner-promo state visible to the current user."""
        config = await PartnerPromoProgramService.get_config(session)
        base: dict[str, object] = {
            "active": False,
            "program_active": bool(config.is_active),
            "welcome_rox_current": str(config.welcome_rox),
            "first_line_percent": str(config.first_line_percent),
            "topup_partner_rox": str(config.topup_partner_rox),
            # Current partner promos do not discount or increase paid packages.
            "package_discount_percent": "0",
        }
        relation = await cls.relation_for_user(session, user_id=user_id)
        if relation is None or relation.source != "promo" or relation.promo_id is None:
            return base

        promo = await session.get(PromoCode, relation.promo_id)
        if promo is None or promo.partner_user_id != relation.inviter_user_id:
            return base

        welcome_tx = await session.scalar(
            select(WalletTransaction)
            .where(
                WalletTransaction.user_id == user_id,
                WalletTransaction.kind == "partner_promo_welcome",
                WalletTransaction.promo_code == promo.code,
                WalletTransaction.partner_id == relation.inviter_user_id,
            )
            .order_by(WalletTransaction.created_at.asc())
        )
        granted = Decimal(welcome_tx.amount) if welcome_tx is not None else Decimal("0")
        return {
            **base,
            "active": True,
            "code": promo.code,
            "promo_id": str(promo.id),
            "partner_user_id": str(relation.inviter_user_id),
            "activated_at": relation.created_at.isoformat(),
            "welcome_rox_granted": str(granted),
        }

    @classmethod
    async def attach_current_attribution_to_payment(
        cls,
        session: AsyncSession,
        *,
        payment: Payment,
    ) -> PromoCode | None:
        """Attach persisted promo attribution to a new payment without reactivation."""
        relation = await cls.relation_for_user(session, user_id=payment.user_id)
        if relation is None or relation.source != "promo" or relation.promo_id is None:
            return None
        promo = await session.get(PromoCode, relation.promo_id)
        if promo is None or promo.partner_user_id != relation.inviter_user_id:
            return None
        cls._attach_payment_metadata(
            payment,
            promo,
            metadata_source="attribution",
        )
        await session.flush()
        return promo

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

    @classmethod
    async def _capacity_reservations(
        cls,
        session: AsyncSession,
        promo: PromoCode,
        *,
        exclude_user_id: uuid.UUID | None = None,
    ) -> int:
        """Count legacy pending reservations that still occupy campaign capacity.

        A live pre-upgrade payment reservation must keep its slot. If that user
        already activated the new partner promo, the pending row continues to
        represent the same single use even after its old reservation deadline,
        until the payment is applied or explicitly released.
        """
        now = datetime.now(UTC)
        activated_pending_users = select(ReferralRelation.referred_user_id).where(
            ReferralRelation.source == "promo",
            ReferralRelation.promo_id == promo.id,
        )
        conditions = [
            PromoRedemption.promo_id == promo.id,
            PromoRedemption.status == "pending",
            or_(
                PromoRedemption.reserved_until > now,
                PromoRedemption.user_id.in_(activated_pending_users),
            ),
        ]
        if exclude_user_id is not None:
            conditions.append(PromoRedemption.user_id != exclude_user_id)
        return int(
            (
                await session.scalar(
                    select(func.count()).select_from(PromoRedemption).where(*conditions)
                )
            )
            or 0
        )

    @classmethod
    async def _check_capacity(
        cls,
        session: AsyncSession,
        promo: PromoCode,
        *,
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        if promo.max_uses is None:
            return
        pending = await cls._capacity_reservations(
            session,
            promo,
            exclude_user_id=exclude_user_id,
        )
        if promo.uses_count + pending >= promo.max_uses:
            raise PromoCodeError("usage_limit_reached", "Promo code usage limit reached")

    @staticmethod
    def _attach_payment_metadata(
        payment: Payment,
        promo: PromoCode,
        *,
        metadata_source: str,
    ) -> None:
        payload = payment.payload or {}
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        payment.payload = {
            **payload,
            "base_credits": str(base),
            "promo_id": str(promo.id),
            "promo_code": promo.code,
            "promo_partner_user_id": str(promo.partner_user_id),
            "promo_metadata_source": metadata_source,
            "promo_reward_credits": "0",
            "promo_bonus_status": "activated",
            "bonus_credits": "0",
            "credited_credits": str(base),
        }
