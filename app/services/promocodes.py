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
)
from app.services.credits import InternalCreditService
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
    Registration ROX are granted by UserService before promo attribution. Future
    paid top-ups are handled by ReferralService; promo activation never grants
    the registration welcome amount or replaces a payment package.
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
        if relation is not None and relation.inviter_user_id != promo.partner_user_id:
            raise PromoCodeError(
                "already_attributed",
                "User is already attributed to another partner",
            )
        if await ReferralAntifraudService._would_create_cycle(
            session,
            visitor_user_id=user_id,
            inviter_user_id=promo.partner_user_id,
        ):
            raise PromoCodeError(
                "referral_cycle",
                "Partner referral admission rejected: referral_cycle",
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
        if relation is not None and relation.inviter_user_id != promo.partner_user_id:
            raise PromoCodeError(
                "already_attributed",
                "User is already attributed to another partner",
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
                else "referral_cycle"
                if admission.reason == "referral_cycle"
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

        # Current clients resend the persisted code as part of their idempotent
        # checkout intent. The promo is available only when the customer
        # explicitly submits it for this payment; persisted referral attribution
        # alone must not mark future top-ups as promo purchases.
        relation = await cls.relation_for_user(session, user_id=payment.user_id)
        if relation is not None and relation.source == "promo" and relation.promo_id is not None:
            attributed = await session.get(PromoCode, relation.promo_id)
            if (
                attributed is not None
                and attributed.code == normalized
                and attributed.partner_user_id == relation.inviter_user_id
            ):
                cls._attach_payment_metadata(
                    payment,
                    attributed,
                    metadata_source="activation",
                )
                await session.flush()
                return attributed

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
        """Apply a payment-time promo entitlement exactly once after settlement.

        New payments use the package-owned `promo_package_bonus_credits` field.
        Legacy in-flight reservations keep their old accounting path so a deploy
        cannot change already-created invoices.
        """
        payload = payment.payload or {}
        base = Decimal(str(payload.get("base_credits") or payment.rox_amount))
        # Before package bonuses were introduced, bonus_credits belonged to
        # the legacy payment-promo promise. Never reinterpret that legacy field
        # as a package gift or it would be counted twice on completion.
        package_bonus = Decimal(str(payload.get("package_bonus_credits") or "0"))

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
                    total_bonus = package_bonus + reward
                    payment.payload = {
                        **payload,
                        "promo_bonus_status": "applied",
                        "promo_bonus_credits": str(reward),
                        "promo_reward_credits": str(reward),
                        "bonus_credits": str(total_bonus),
                        "credited_credits": str(base + total_bonus),
                    }
                    return reward

            redemption.status = "released"
            redemption.reserved_until = None
            redemption.redeemed_at = None

        # New package contract: the package itself owns the promo-gated bonus.
        # Presence of this field distinguishes new payments from legacy in-flight
        # payments that used the old threshold + separate bonus model.
        if "promo_package_bonus_credits" in payload:
            reward = Decimal(str(payload.get("promo_package_bonus_credits") or "0"))
            promo_code = cls.normalize(str(payload.get("promo_code") or ""))
            if not promo_code or reward <= 0:
                payment.payload = {
                    **payload,
                    "promo_bonus_status": "no_promo" if not promo_code else "no_bonus",
                    "promo_bonus_credits": "0",
                    "promo_reward_credits": "0",
                    "bonus_credits": str(package_bonus),
                    "credited_credits": str(base + package_bonus),
                }
                return Decimal("0")

            relation = await session.scalar(
                select(ReferralRelation)
                .where(ReferralRelation.referred_user_id == payment.user_id)
                .with_for_update()
            )
            promo = None
            if relation is not None and relation.source == "promo" and relation.promo_id is not None:
                promo = await session.get(PromoCode, relation.promo_id)
            config = await PartnerPromoProgramService.get_config(session)
            eligible = (
                config.is_active
                and relation is not None
                and promo is not None
                and promo.is_active
                and promo.partner_user_id == relation.inviter_user_id
                and promo.code == promo_code
            )
            if not eligible:
                payment.payload = {
                    **payload,
                    "promo_bonus_status": "program_inactive" if not config.is_active else "invalid",
                    "promo_bonus_credits": "0",
                    "promo_reward_credits": "0",
                    "bonus_credits": str(package_bonus),
                    "credited_credits": str(base + package_bonus),
                }
                return Decimal("0")

            assert relation is not None and promo is not None
            await WalletService.credit(
                session,
                user_id=payment.user_id,
                amount=reward,
                kind="partner_promo_user_topup_bonus",
                reference_type="payment",
                reference_id=str(payment.id),
                idempotency_key=f"payment:{payment.id}:partner-promo-user-topup",
                reason="partner_promo_package_bonus",
                promo_code=promo.code,
                partner_id=relation.inviter_user_id,
                referral_user_id=payment.user_id,
                payment_id=payment.id,
            )
            total_bonus = package_bonus + reward
            payment.payload = {
                **payload,
                "promo_bonus_status": "applied",
                "promo_bonus_credits": str(reward),
                "promo_reward_credits": str(reward),
                "bonus_credits": str(total_bonus),
                "credited_credits": str(base + total_bonus),
            }
            return reward

        promo_code = cls.normalize(str(payload.get("promo_code") or ""))
        if not promo_code:
            return Decimal("0")

        relation = await session.scalar(
            select(ReferralRelation)
            .where(ReferralRelation.referred_user_id == payment.user_id)
            .with_for_update()
        )
        promo = None
        if (
            relation is not None
            and relation.source == "promo"
            and relation.promo_id is not None
        ):
            promo = await session.get(PromoCode, relation.promo_id)
        if (
            relation is None
            or promo is None
            or promo.partner_user_id != relation.inviter_user_id
            or promo.code != promo_code
        ):
            payment.payload = {
                **payload,
                "promo_bonus_status": "activated",
                "promo_bonus_credits": "0",
                "promo_reward_credits": "0",
                "bonus_credits": str(package_bonus),
                "credited_credits": str(base + package_bonus),
            }
            return Decimal("0")

        config = await PartnerPromoProgramService.get_config(session)
        payment_rub_basis = (
            Decimal(payment.amount)
            if payment.currency.upper() == "RUB"
            else InternalCreditService.rubles_for(base)
        )
        eligible = (
            config.is_active
            and payment_rub_basis >= Decimal(config.topup_user_min_rub)
            and Decimal(config.topup_user_rox) > 0
        )
        if not eligible:
            status = "below_threshold" if config.is_active else "program_inactive"
            payment.payload = {
                **payload,
                "promo_bonus_status": status,
                "promo_bonus_credits": "0",
                "promo_reward_credits": "0",
                "promo_bonus_basis_rub": str(payment_rub_basis),
                "promo_bonus_threshold_rub": str(config.topup_user_min_rub),
                "bonus_credits": str(package_bonus),
                "credited_credits": str(base + package_bonus),
            }
            return Decimal("0")

        reward = Decimal(config.topup_user_rox)
        await WalletService.credit(
            session,
            user_id=payment.user_id,
            amount=reward,
            kind="partner_promo_user_topup_bonus",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment:{payment.id}:partner-promo-user-topup",
            reason="partner_promo_user_topup_bonus",
            promo_code=promo.code,
            partner_id=relation.inviter_user_id,
            referral_user_id=payment.user_id,
            payment_id=payment.id,
        )
        total_bonus = package_bonus + reward
        payment.payload = {
            **payload,
            "promo_bonus_status": "applied",
            "promo_bonus_credits": str(reward),
            "promo_reward_credits": str(reward),
            "promo_bonus_basis_rub": str(payment_rub_basis),
            "promo_bonus_threshold_rub": str(config.topup_user_min_rub),
            "bonus_credits": str(total_bonus),
            "credited_credits": str(base + total_bonus),
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
            "bonus_eligible": False,
            "program_active": bool(config.is_active),
            "registration_welcome_rox": str(config.welcome_rox),
            # Compatibility fields describe promo activation only. Purchase bonus
            # values come from the selected package in the admin tariff.
            "welcome_rox_current": "0",
            "first_line_percent": str(config.first_line_percent),
            "topup_partner_rox": str(config.topup_partner_rox),
            "topup_user_rox": "0",
            "topup_user_min_rub": "0",
            "package_discount_percent": "0",
        }
        relation = await cls.relation_for_user(session, user_id=user_id)
        if relation is None or relation.source != "promo" or relation.promo_id is None:
            return base

        promo = await session.get(PromoCode, relation.promo_id)
        if promo is None or promo.partner_user_id != relation.inviter_user_id:
            return base

        return {
            **base,
            "active": True,
            "bonus_eligible": bool(config.is_active and promo.is_active),
            "code": promo.code,
            "promo_id": str(promo.id),
            "partner_user_id": str(relation.inviter_user_id),
            "activated_at": relation.created_at.isoformat(),
            # Promo activation itself never credits ROX. Registration welcome
            # belongs to the account lifecycle and is intentionally not surfaced here.
            "welcome_rox_granted": "0",
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
        package_bonus = Decimal(str(payload.get("package_bonus_credits") or "0"))
        promo_package_bonus = Decimal(str(payload.get("promo_package_bonus_credits") or "0"))
        payment.payload = {
            **payload,
            "base_credits": str(base),
            "package_bonus_credits": str(package_bonus),
            "promo_package_bonus_credits": str(promo_package_bonus),
            "promo_bonus_credits": "0",
            "promo_id": str(promo.id),
            "promo_code": promo.code,
            "promo_partner_user_id": str(promo.partner_user_id),
            "promo_metadata_source": metadata_source,
            "promo_reward_credits": "0",
            "promo_bonus_status": "activated",
            "bonus_credits": str(package_bonus),
            "credited_credits": str(base + package_bonus),
        }
