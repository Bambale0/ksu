from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.creator_partner_models import (
    CreatorPartnershipAgreement,
    CreatorPartnershipApplication,
    CreatorPartnershipGrant,
)
from app.db.models import AdminAccount, AdminSession, User
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.admin_security import AdminAuditService
from app.services.notifications import NotificationService
from app.services.wallet import WalletService

ApplicationDecision = Literal["approved", "rejected"]
AgreementStatus = Literal["active", "paused", "ended"]
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def current_period() -> str:
    return utcnow().strftime("%Y-%m")


def period_start(period: str) -> date:
    if not _PERIOD_RE.fullmatch(period):
        raise ValueError("Period must use YYYY-MM")
    year, month = (int(part) for part in period.split("-", 1))
    return date(year, month, 1)


class CreatorPartnershipConflict(RuntimeError):
    pass


class CreatorPartnershipService:
    @staticmethod
    def _money(value: Decimal | str | int | float) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _application_view(item: CreatorPartnershipApplication) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "channel_name": item.channel_name,
            "channel_url": item.channel_url,
            "audience_size": item.audience_size,
            "average_views": item.average_views,
            "cooperation_format": item.cooperation_format,
            "message": item.message,
            "status": item.status,
            "decision_note": item.decision_note,
            "decided_at": item.decided_at.isoformat() if item.decided_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    def _agreement_view(item: CreatorPartnershipAgreement) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "application_id": str(item.application_id),
            "status": item.status,
            "terms_summary": item.terms_summary,
            "monthly_rox": str(item.monthly_rox),
            "terms": item.terms or {},
            "starts_on": item.starts_on.isoformat(),
            "ends_on": item.ends_on.isoformat() if item.ends_on else None,
            "approved_at": item.approved_at.isoformat(),
        }

    @staticmethod
    def _grant_view(item: CreatorPartnershipGrant) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "agreement_id": str(item.agreement_id),
            "period": item.period,
            "amount_rox": str(item.amount_rox),
            "source": item.source,
            "note": item.note,
            "created_at": item.created_at.isoformat(),
        }

    @classmethod
    async def status(cls, session: AsyncSession, *, user_id: uuid.UUID) -> dict[str, Any]:
        application = await session.scalar(
            select(CreatorPartnershipApplication)
            .where(CreatorPartnershipApplication.user_id == user_id)
            .order_by(CreatorPartnershipApplication.created_at.desc())
            .limit(1)
        )
        agreement = await session.scalar(
            select(CreatorPartnershipAgreement)
            .where(CreatorPartnershipAgreement.user_id == user_id)
            .order_by(CreatorPartnershipAgreement.created_at.desc())
            .limit(1)
        )
        grants = list(
            (
                await session.scalars(
                    select(CreatorPartnershipGrant)
                    .where(CreatorPartnershipGrant.user_id == user_id)
                    .order_by(CreatorPartnershipGrant.period.desc())
                    .limit(24)
                )
            ).all()
        )
        return {
            "application": cls._application_view(application) if application else None,
            "agreement": cls._agreement_view(agreement) if agreement else None,
            "grants": [cls._grant_view(item) for item in grants],
            "total_granted_rox": str(
                cls._money(
                    (await session.scalar(
                        select(func.coalesce(func.sum(CreatorPartnershipGrant.amount_rox), 0)).where(
                            CreatorPartnershipGrant.user_id == user_id
                        )
                    ))
                    or 0
                )
            ),
        }

    @classmethod
    async def submit_application(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel_name: str,
        channel_url: str,
        audience_size: int,
        average_views: int | None,
        cooperation_format: str,
        message: str,
        idempotency_key: str,
    ) -> tuple[CreatorPartnershipApplication, bool]:
        key = idempotency_key.strip()
        if not key or len(key) > 160:
            raise ValueError("Valid Idempotency-Key is required")
        existing = await session.scalar(
            select(CreatorPartnershipApplication).where(
                CreatorPartnershipApplication.idempotency_key == key
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise CreatorPartnershipConflict("Idempotency key already belongs to another user")
            return existing, True

        if not channel_url.startswith("https://"):
            raise ValueError("Channel URL must use HTTPS")
        if audience_size < 1 or audience_size > 100_000_000:
            raise ValueError("Audience size is out of range")
        if average_views is not None and not 0 <= average_views <= 100_000_000:
            raise ValueError("Average views is out of range")

        # Serialize all creator partnership admission for one user. This closes the
        # check-then-insert race for different idempotency keys and for application
        # submission racing with an admin approval.
        locked_user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if locked_user is None:
            raise LookupError("User not found")

        existing = await session.scalar(
            select(CreatorPartnershipApplication).where(
                CreatorPartnershipApplication.idempotency_key == key
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise CreatorPartnershipConflict("Idempotency key already belongs to another user")
            return existing, True

        active = await session.scalar(
            select(CreatorPartnershipAgreement).where(
                CreatorPartnershipAgreement.user_id == user_id,
                CreatorPartnershipAgreement.status.in_(("active", "paused")),
            )
        )
        if active is not None:
            raise CreatorPartnershipConflict("Creator partnership agreement already exists")
        pending = await session.scalar(
            select(CreatorPartnershipApplication).where(
                CreatorPartnershipApplication.user_id == user_id,
                CreatorPartnershipApplication.status == "pending",
            )
        )
        if pending is not None:
            raise CreatorPartnershipConflict("Creator partnership application is already pending")

        item = CreatorPartnershipApplication(
            user_id=user_id,
            idempotency_key=key,
            channel_name=channel_name.strip()[:160],
            channel_url=channel_url.strip()[:2048],
            audience_size=audience_size,
            average_views=average_views,
            cooperation_format=cooperation_format.strip()[:160],
            message=message.strip()[:4000],
            status="pending",
        )
        if not item.channel_name or not item.cooperation_format:
            raise ValueError("Channel name and cooperation format are required")
        session.add(item)
        await session.flush()
        await NotificationService.create(
            session,
            user_id=user_id,
            kind="creator_partnership_application",
            title="Заявка на партнёрство принята",
            body="ROXY получила заявку. Условия будут рассчитаны индивидуально после проверки канала.",
        )
        return item, False

    @classmethod
    async def list_applications(
        cls,
        session: AsyncSession,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        stmt = select(CreatorPartnershipApplication, User).join(
            User, User.id == CreatorPartnershipApplication.user_id
        )
        count_stmt = select(func.count()).select_from(CreatorPartnershipApplication)
        if status:
            stmt = stmt.where(CreatorPartnershipApplication.status == status)
            count_stmt = count_stmt.where(CreatorPartnershipApplication.status == status)
        bounded_limit = max(1, min(limit, 100))
        bounded_offset = max(0, min(offset, 100_000))
        rows = (
            await session.execute(
                stmt.order_by(CreatorPartnershipApplication.created_at.desc())
                .offset(bounded_offset)
                .limit(bounded_limit)
            )
        ).all()
        return {
            "items": [
                {
                    **cls._application_view(item),
                    "user": {
                        "id": str(user.id),
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "first_name": user.first_name,
                    },
                }
                for item, user in rows
            ],
            "total": int((await session.scalar(count_stmt)) or 0),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @classmethod
    async def decide_application(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        application_id: uuid.UUID,
        decision: ApplicationDecision,
        decision_note: str,
        terms_summary: str | None,
        monthly_rox: Decimal | None,
        terms: dict[str, Any] | None,
        starts_on: date | None,
        ends_on: date | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "creator_partnership.decide", confirmed=confirmed)
        if decision == "approved":
            if monthly_rox is None or cls._money(monthly_rox) <= 0:
                raise ValueError("Positive monthly_rox is required for approval")
            if not (terms_summary or "").strip():
                raise ValueError("Terms summary is required for approval")
        payload = {
            "decision": decision,
            "decision_note": decision_note,
            "terms_summary": terms_summary,
            "monthly_rox": str(monthly_rox) if monthly_rox is not None else None,
            "terms": terms or {},
            "starts_on": starts_on.isoformat() if starts_on else None,
            "ends_on": ends_on.isoformat() if ends_on else None,
        }

        async def operation() -> dict[str, Any]:
            item = await session.scalar(
                select(CreatorPartnershipApplication)
                .where(CreatorPartnershipApplication.id == application_id)
                .with_for_update()
            )
            if item is None:
                raise LookupError("Creator partnership application not found")
            if item.status != "pending":
                raise CreatorPartnershipConflict("Application has already been decided")
            now = utcnow()
            item.status = decision
            item.decision_note = decision_note.strip()[:4000] or None
            item.decided_by_admin_id = admin.id
            item.decided_at = now
            agreement = None
            if decision == "approved":
                locked_user = await session.scalar(
                    select(User).where(User.id == item.user_id).with_for_update()
                )
                if locked_user is None:
                    raise LookupError("Creator partnership user not found")
                current = await session.scalar(
                    select(CreatorPartnershipAgreement).where(
                        CreatorPartnershipAgreement.user_id == item.user_id,
                        CreatorPartnershipAgreement.status.in_(("active", "paused")),
                    )
                )
                if current is not None:
                    raise CreatorPartnershipConflict("User already has an active creator agreement")
                start = starts_on or now.date().replace(day=1)
                if ends_on is not None and ends_on < start:
                    raise ValueError("Agreement end date cannot be before start date")
                agreement = CreatorPartnershipAgreement(
                    application_id=item.id,
                    user_id=item.user_id,
                    status="active",
                    terms_summary=str(terms_summary or "").strip()[:4000],
                    monthly_rox=cls._money(monthly_rox or 0),
                    terms=terms or {},
                    starts_on=start,
                    ends_on=ends_on,
                    approved_by_admin_id=admin.id,
                    approved_at=now,
                )
                session.add(agreement)
                await session.flush()
                await NotificationService.create(
                    session,
                    user_id=item.user_id,
                    kind="creator_partnership_approved",
                    title="Creator-партнёрство одобрено",
                    body=f"Ваши условия согласованы. Ежемесячный лимит: {agreement.monthly_rox} ROX.",
                )
            else:
                await NotificationService.create(
                    session,
                    user_id=item.user_id,
                    kind="creator_partnership_rejected",
                    title="Статус заявки на партнёрство",
                    body=item.decision_note or "Сейчас мы не можем подтвердить сотрудничество. Можно подать новую заявку позже.",
                )
            await AdminAuditService.record(
                session,
                action="admin.creator_partnership.decided",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="creator_partnership_application",
                resource_id=str(item.id),
                reason=decision_note,
                metadata={
                    "decision": decision,
                    "agreement_id": str(agreement.id) if agreement else None,
                    "monthly_rox": str(agreement.monthly_rox) if agreement else None,
                },
            )
            return {
                "application": cls._application_view(item),
                "agreement": cls._agreement_view(agreement) if agreement else None,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="creator_partnership.decide",
            target_id=str(application_id),
            request_payload=payload,
            operation=operation,
        )

    @classmethod
    async def update_agreement(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        agreement_id: uuid.UUID,
        status: AgreementStatus,
        terms_summary: str,
        monthly_rox: Decimal,
        terms: dict[str, Any],
        ends_on: date | None,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "creator_partnership.update", confirmed=confirmed)
        amount = cls._money(monthly_rox)
        if amount <= 0:
            raise ValueError("monthly_rox must be positive")
        if not terms_summary.strip():
            raise ValueError("Terms summary is required")
        payload = {
            "status": status,
            "terms_summary": terms_summary,
            "monthly_rox": str(amount),
            "terms": terms,
            "ends_on": ends_on.isoformat() if ends_on else None,
            "reason": reason,
        }

        async def operation() -> dict[str, Any]:
            agreement = await session.scalar(
                select(CreatorPartnershipAgreement)
                .where(CreatorPartnershipAgreement.id == agreement_id)
                .with_for_update()
            )
            if agreement is None:
                raise LookupError("Creator partnership agreement not found")
            before = cls._agreement_view(agreement)
            if ends_on is not None and ends_on < agreement.starts_on:
                raise ValueError("Agreement end date cannot be before start date")
            agreement.status = status
            agreement.terms_summary = terms_summary.strip()[:4000]
            agreement.monthly_rox = amount
            agreement.terms = terms
            agreement.ends_on = ends_on
            await NotificationService.create(
                session,
                user_id=agreement.user_id,
                kind="creator_partnership_terms_updated",
                title="Условия Creator-партнёрства обновлены",
                body=f"Статус: {status}. Ежемесячный лимит: {amount} ROX.",
            )
            await AdminAuditService.record(
                session,
                action="admin.creator_partnership.updated",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="creator_partnership_agreement",
                resource_id=str(agreement.id),
                reason=reason,
                metadata={"before": before, "after": cls._agreement_view(agreement)},
            )
            return cls._agreement_view(agreement)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="creator_partnership.update",
            target_id=str(agreement_id),
            request_payload=payload,
            operation=operation,
        )

    @classmethod
    async def grant_agreement_period(
        cls,
        session: AsyncSession,
        *,
        agreement: CreatorPartnershipAgreement,
        period: str,
        source: Literal["scheduler", "admin"],
        granted_by_admin_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> tuple[CreatorPartnershipGrant, bool]:
        start = period_start(period)
        locked = await session.scalar(
            select(CreatorPartnershipAgreement)
            .where(CreatorPartnershipAgreement.id == agreement.id)
            .with_for_update()
        )
        if locked is None:
            raise LookupError("Creator partnership agreement not found")
        agreement = locked
        if agreement.status != "active":
            raise CreatorPartnershipConflict("Agreement is not active")
        if start < agreement.starts_on.replace(day=1):
            raise ValueError("Grant period is before agreement start")
        if agreement.ends_on is not None and start > agreement.ends_on.replace(day=1):
            raise ValueError("Grant period is after agreement end")
        existing = await session.scalar(
            select(CreatorPartnershipGrant).where(
                CreatorPartnershipGrant.agreement_id == agreement.id,
                CreatorPartnershipGrant.period == period,
            )
        )
        if existing is not None:
            return existing, True
        amount = cls._money(agreement.monthly_rox)
        tx = await WalletService.credit(
            session,
            user_id=agreement.user_id,
            amount=amount,
            kind="creator_monthly_grant",
            reference_type="creator_partnership",
            reference_id=str(agreement.id),
            idempotency_key=f"creator-grant:{agreement.id}:{period}",
        )
        grant = CreatorPartnershipGrant(
            agreement_id=agreement.id,
            user_id=agreement.user_id,
            period=period,
            amount_rox=amount,
            wallet_transaction_id=tx.id,
            granted_by_admin_id=granted_by_admin_id,
            source=source,
            note=(note or "").strip()[:4000] or None,
        )
        session.add(grant)
        await session.flush()
        await NotificationService.create(
            session,
            user_id=agreement.user_id,
            kind="creator_partnership_grant",
            title="Начисление по Creator-партнёрству",
            body=f"За {period} начислено {amount} бонусных ROX для создания контента.",
        )
        return grant, False

    @classmethod
    async def admin_grant(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        agreement_id: uuid.UUID,
        period: str,
        note: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "creator_partnership.grant",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        period_start(period)

        async def operation() -> dict[str, Any]:
            agreement = await session.scalar(
                select(CreatorPartnershipAgreement)
                .where(CreatorPartnershipAgreement.id == agreement_id)
                .with_for_update()
            )
            if agreement is None:
                raise LookupError("Creator partnership agreement not found")
            grant, replayed = await cls.grant_agreement_period(
                session,
                agreement=agreement,
                period=period,
                source="admin",
                granted_by_admin_id=admin.id,
                note=note,
            )
            await AdminAuditService.record(
                session,
                action="admin.creator_partnership.granted",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="creator_partnership_agreement",
                resource_id=str(agreement.id),
                reason=note,
                metadata={
                    "grant_id": str(grant.id),
                    "period": period,
                    "amount_rox": str(grant.amount_rox),
                    "grant_replayed": replayed,
                },
            )
            return {"grant": cls._grant_view(grant), "grant_replayed": replayed}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="creator_partnership.grant",
            target_id=str(agreement_id),
            request_payload={"period": period, "note": note},
            operation=operation,
        )

    @classmethod
    async def grant_due_current_period(cls, session: AsyncSession) -> int:
        period = current_period()
        start = period_start(period)
        agreements = list(
            (
                await session.scalars(
                    select(CreatorPartnershipAgreement).where(
                        CreatorPartnershipAgreement.status == "active",
                        CreatorPartnershipAgreement.starts_on <= start,
                        (
                            CreatorPartnershipAgreement.ends_on.is_(None)
                            | (CreatorPartnershipAgreement.ends_on >= start)
                        ),
                    )
                )
            ).all()
        )
        created = 0
        for agreement in agreements:
            _grant, replayed = await cls.grant_agreement_period(
                session,
                agreement=agreement,
                period=period,
                source="scheduler",
            )
            if not replayed:
                created += 1
        return created
