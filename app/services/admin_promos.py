from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, PromoCode, User
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.partner_promo_program import PartnerPromoProgramService


class AdminPromoService:
    @staticmethod
    async def list_promos(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        limit: int = 100,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "promocodes.read")
        rows = list(
            (
                await session.scalars(
                    select(PromoCode)
                    .order_by(PromoCode.created_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {"items": [AdminPromoService._view(item) for item in rows]}

    @staticmethod
    async def lookup(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        query: str,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "promocodes.read")
        raw = query.strip()
        promo = None
        try:
            promo_id = uuid.UUID(raw)
        except ValueError:
            promo_id = None
        if promo_id is not None:
            promo = await session.get(PromoCode, promo_id)
        if promo is None:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.code == raw.upper())
            )
        if promo is None:
            raise LookupError("Promo code not found")
        return AdminPromoService._view(promo)

    @staticmethod
    def _view(item: PromoCode) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "code": item.code,
            "partner_user_id": str(item.partner_user_id) if item.partner_user_id else None,
            "max_uses": item.max_uses,
            "uses_count": item.uses_count,
            "is_active": item.is_active,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    def _require_partner_before_activation(item: PromoCode) -> None:
        if item.partner_user_id is None:
            raise ValueError("Promo code must have a partner before activation")

    @staticmethod
    async def program_settings(
        session: AsyncSession,
        *,
        admin: AdminAccount,
    ) -> dict[str, object]:
        AdminPolicy.require_permission(admin, "promocodes.read")
        config = await PartnerPromoProgramService.get_config(session)
        return PartnerPromoProgramService.view(config)

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        code: str,
        partner_user_id: uuid.UUID | None,
        max_uses: int | None,
        expires_at: datetime | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        normalized = code.strip().upper()
        if partner_user_id is None:
            raise ValueError(
                "partner_user_id is required: every active promo code must belong to a partner"
            )
        if len(normalized) < 3 or len(normalized) > 64:
            raise ValueError("Promo code must contain 3..64 characters")
        if not all(char.isalnum() or char in {"_", "-"} for char in normalized):
            raise ValueError("Promo code contains unsupported characters")
        if max_uses is not None and not 1 <= max_uses <= 10_000_000:
            raise ValueError("Invalid promo max_uses")
        if expires_at is not None and expires_at.utcoffset() is None:
            raise ValueError("Promo expiration must include timezone")
        payload = {
            "code": normalized,
            "partner_user_id": str(partner_user_id) if partner_user_id else None,
            "max_uses": max_uses,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        async def operation() -> dict[str, Any]:
            if expires_at is not None and expires_at <= datetime.now(UTC):
                raise ValueError("Promo expiration must be in the future")
            if await session.scalar(select(PromoCode).where(PromoCode.code == normalized)):
                raise ValueError("Promo code already exists")
            if partner_user_id is not None:
                partner = await session.get(User, partner_user_id)
                if partner is None or not partner.is_active:
                    raise ValueError("Promo partner must be an active user")
            config = await PartnerPromoProgramService.get_config(session)
            promo = PromoCode(
                code=normalized,
                # Legacy column mirrors the current welcome grant for compatibility,
                # but runtime economics are always read from the global config.
                reward_amount=Decimal(config.welcome_rox),
                partner_user_id=partner_user_id,
                max_uses=max_uses,
                is_active=True,
                expires_at=expires_at,
            )
            session.add(promo)
            await session.flush()
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=normalized,
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def update_campaign(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        promo_id: uuid.UUID,
        max_uses: int | None,
        expires_at: datetime | None,
        is_active: bool | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        if max_uses is None and expires_at is None and is_active is None:
            raise ValueError("No promo changes supplied")
        if max_uses is not None and not 1 <= max_uses <= 10_000_000:
            raise ValueError("Invalid promo max_uses")
        if expires_at is not None:
            if expires_at.utcoffset() is None:
                raise ValueError("Promo expiration must include timezone")
            if expires_at <= datetime.now(UTC):
                raise ValueError("Promo expiration must be in the future")

        payload = {
            "max_uses": max_uses,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "is_active": is_active,
        }

        async def operation() -> dict[str, Any]:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
            )
            if promo is None:
                raise LookupError("Promo code not found")
            if max_uses is not None:
                if max_uses < promo.uses_count:
                    raise ValueError("max_uses cannot be below uses_count")
                promo.max_uses = max_uses
            if expires_at is not None:
                promo.expires_at = expires_at
            if is_active is not None:
                if is_active:
                    AdminPromoService._require_partner_before_activation(promo)
                promo.is_active = is_active
            await session.flush()
            await session.refresh(promo)
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=str(promo_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def set_partner(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        promo_id: uuid.UUID,
        partner_user_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        payload = {"partner_user_id": str(partner_user_id)}

        async def operation() -> dict[str, Any]:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
            )
            if promo is None:
                raise LookupError("Promo code not found")
            partner = await session.get(User, partner_user_id)
            if partner is None or not partner.is_active:
                raise ValueError("Promo partner must be an active user")
            if (
                promo.partner_user_id is not None
                and promo.partner_user_id != partner_user_id
                and promo.uses_count > 0
            ):
                raise ValueError("Used promo code partner cannot be changed")
            promo.partner_user_id = partner_user_id
            await session.flush()
            await session.refresh(promo)
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=str(promo_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def set_active(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        promo_id: uuid.UUID,
        is_active: bool,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        payload = {"is_active": is_active}

        async def operation() -> dict[str, Any]:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
            )
            if promo is None:
                raise LookupError("Promo code not found")
            if is_active:
                AdminPromoService._require_partner_before_activation(promo)
            promo.is_active = is_active
            await session.flush()
            await session.refresh(promo)
            return AdminPromoService._view(promo)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id=str(promo_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def update_program(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        welcome_rox: Decimal,
        first_line_percent: Decimal,
        topup_partner_rox: Decimal,
        is_active: bool,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, object], bool]:
        AdminPolicy.authorize_action(admin, "promos.manage", confirmed=confirmed)
        PartnerPromoProgramService.validate_values(
            welcome_rox=welcome_rox,
            first_line_percent=first_line_percent,
            topup_partner_rox=topup_partner_rox,
        )
        payload = {
            "welcome_rox": str(welcome_rox),
            "first_line_percent": str(first_line_percent),
            "topup_partner_rox": str(topup_partner_rox),
            "is_active": is_active,
        }

        async def operation() -> dict[str, object]:
            config = await PartnerPromoProgramService.get_config(session, for_update=True)
            config.welcome_rox = welcome_rox
            config.first_line_percent = first_line_percent
            config.topup_partner_rox = topup_partner_rox
            config.is_active = is_active
            await session.flush()
            await session.refresh(config)
            return PartnerPromoProgramService.view(config)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="promos.manage",
            target_id="partner-promo-program",
            request_payload=payload,
            operation=operation,
        )
