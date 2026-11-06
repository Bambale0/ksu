from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.admin_models import SupportOutbox, SupportTicketAdminState
from app.db.models import AdminAccount, AdminSession, SupportMessage, SupportTicket, User
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.admin_security import AdminAuditService
from app.services.admin_users import AdminUserService

SupportStatus = Literal["open", "in_progress", "resolved", "closed"]
SupportPriority = Literal["low", "normal", "high", "urgent"]


def _ticket_view(
    ticket: SupportTicket,
    state: SupportTicketAdminState | None,
    user: User,
    latest: SupportMessage | None,
    *,
    can_view_pii: bool,
) -> dict[str, Any]:
    activity_at = max(ticket.updated_at, latest.created_at) if latest else ticket.updated_at
    return {
        "id": str(ticket.id),
        "user_id": str(ticket.user_id),
        "user": {
            "id": str(user.id),
            "telegram_id": (
                user.telegram_id if can_view_pii
                else AdminUserService._masked_telegram_id(user.telegram_id)
            ),
            "username": user.username if can_view_pii else None,
            "first_name": user.first_name if can_view_pii else "[restricted]",
            "last_name": user.last_name if can_view_pii else None,
        },
        "topic": ticket.topic,
        "status": ticket.status,
        "assigned_admin_id": (
            str(state.assigned_admin_id) if state and state.assigned_admin_id else None
        ),
        "priority": state.priority if state else "normal",
        "created_at": ticket.created_at.isoformat(),
        "updated_at": activity_at.isoformat(),
        "needs_reply": bool(
            latest and not latest.is_admin and ticket.status in {"open", "in_progress"}
        ),
        "last_message": {
            "id": str(latest.id),
            "body": latest.body[:240],
            "is_admin": latest.is_admin,
            "created_at": latest.created_at.isoformat(),
        } if latest else None,
    }


def _message_view(message: SupportMessage, delivery: SupportOutbox | None) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "sender_user_id": str(message.user_id) if message.user_id else None,
        "is_admin": message.is_admin,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
        "outbox_id": str(delivery.id) if delivery else None,
        "delivery_status": delivery.status if delivery else None,
        "delivery_attempts": delivery.attempts if delivery else 0,
        "sent_at": delivery.sent_at.isoformat() if delivery and delivery.sent_at else None,
    }


class SupportTicketClosedError(ValueError):
    pass


class AdminSupportService:
    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "support.read")
        can_pii = AdminPolicy.has_permission(admin, "users.pii")
        limit = max(1, min(limit, 100))
        offset = max(0, min(offset, 100_000))
        filters = []
        if status:
            filters.append(SupportTicket.status == status)
        if q and q.strip():
            value = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{value}%"
            searchable = [
                SupportTicket.topic.ilike(pattern, escape="\\"),
                cast(User.id, String).ilike(pattern, escape="\\"),
                cast(SupportTicket.id, String).ilike(pattern, escape="\\"),
            ]
            if can_pii:
                searchable.extend([
                    User.username.ilike(pattern, escape="\\"),
                    User.first_name.ilike(pattern, escape="\\"),
                    User.last_name.ilike(pattern, escape="\\"),
                    cast(User.telegram_id, String).ilike(pattern, escape="\\"),
                ])
            filters.append(or_(*searchable))
        latest_alias = aliased(SupportMessage)
        latest_id = (
            select(latest_alias.id)
            .where(latest_alias.ticket_id == SupportTicket.id)
            .order_by(latest_alias.created_at.desc(), latest_alias.id.desc())
            .limit(1)
            .correlate(SupportTicket)
            .scalar_subquery()
        )
        query = (
            select(SupportTicket, SupportTicketAdminState, User, SupportMessage)
            .join(User, User.id == SupportTicket.user_id)
            .outerjoin(SupportTicketAdminState, SupportTicketAdminState.ticket_id == SupportTicket.id)
            .outerjoin(SupportMessage, SupportMessage.id == latest_id)
            .where(*filters)
        )
        total = int((await session.scalar(
            select(func.count()).select_from(SupportTicket)
            .join(User, User.id == SupportTicket.user_id).where(*filters)
        )) or 0)
        rows = (await session.execute(
            query.order_by(
                func.greatest(SupportTicket.updated_at, SupportMessage.created_at).desc(),
                SupportTicket.id.desc(),
            ).offset(offset).limit(limit)
        )).all()
        return {
            "items": [
                _ticket_view(ticket, state, user, latest, can_view_pii=can_pii)
                for ticket, state, user, latest in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }

    @staticmethod
    async def get_ticket(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        ticket_id: uuid.UUID,
        message_limit: int = 100,
        before: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "support.read")
        can_pii = AdminPolicy.has_permission(admin, "users.pii")
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")
        user = await session.get(User, ticket.user_id)
        if user is None:
            raise LookupError("Ticket user not found")
        state = await session.get(SupportTicketAdminState, ticket_id)
        latest = await session.scalar(
            select(SupportMessage).where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc()).limit(1)
        )
        statement = (
            select(SupportMessage, SupportOutbox)
            .outerjoin(SupportOutbox, SupportOutbox.message_id == SupportMessage.id)
            .where(SupportMessage.ticket_id == ticket_id)
        )
        if before is not None:
            cursor = await session.scalar(select(SupportMessage).where(
                SupportMessage.id == before, SupportMessage.ticket_id == ticket_id,
            ))
            if cursor is None:
                raise LookupError("Message cursor not found")
            statement = statement.where(or_(
                SupportMessage.created_at < cursor.created_at,
                and_(SupportMessage.created_at == cursor.created_at, SupportMessage.id < cursor.id),
            ))
        limit = max(1, min(message_limit, 500))
        rows = (await session.execute(
            statement.order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc()).limit(limit + 1)
        )).all()
        has_more = len(rows) > limit
        page = list(reversed(rows[:limit]))
        result = _ticket_view(ticket, state, user, latest, can_view_pii=can_pii)
        result.update({
            "messages": [_message_view(message, delivery) for message, delivery in page],
            "messages_total": int((await session.scalar(
                select(func.count()).select_from(SupportMessage).where(SupportMessage.ticket_id == ticket_id)
            )) or 0),
            "messages_has_more": has_more,
            "messages_before": str(page[0][0].id) if has_more and page else None,
        })
        return result

    @staticmethod
    async def assign_ticket(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        ticket_id: uuid.UUID,
        assigned_admin_id: uuid.UUID | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool = True,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "support.assign", confirmed=confirmed)
        payload = {"assigned_admin_id": str(assigned_admin_id) if assigned_admin_id else None}

        async def operation() -> dict[str, Any]:
            ticket = await session.get(SupportTicket, ticket_id)
            if ticket is None:
                raise LookupError("Ticket not found")
            if assigned_admin_id is not None:
                assigned = await session.get(AdminAccount, assigned_admin_id)
                if assigned is None or not assigned.is_active:
                    raise LookupError("Assigned admin not found")
            state = await session.get(SupportTicketAdminState, ticket_id)
            if state is None:
                state = SupportTicketAdminState(ticket_id=ticket_id, priority="normal")
                session.add(state)
            before = state.assigned_admin_id
            state.assigned_admin_id = assigned_admin_id
            await AdminAuditService.record(
                session,
                action="admin.support.assigned",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="support_ticket",
                resource_id=str(ticket_id),
                metadata={
                    "before": str(before) if before else None,
                    "after": str(assigned_admin_id) if assigned_admin_id else None,
                },
            )
            return {"id": str(ticket_id), **payload}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="support.assign",
            target_id=str(ticket_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def update_ticket(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        ticket_id: uuid.UUID,
        status: SupportStatus | None,
        priority: SupportPriority | None,
        idempotency_key: str,
        request_id: str,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "support.update", confirmed=True)
        payload = {"status": status, "priority": priority}

        async def operation() -> dict[str, Any]:
            ticket = await session.scalar(
                select(SupportTicket).where(SupportTicket.id == ticket_id).with_for_update()
            )
            if ticket is None:
                raise LookupError("Ticket not found")
            transitions = {
                "open": {"in_progress", "resolved", "closed"},
                "in_progress": {"open", "resolved", "closed"},
                "resolved": {"open", "closed"},
                "closed": {"open"},
            }
            before_status = ticket.status
            if status and status != ticket.status:
                if status not in transitions.get(ticket.status, set()):
                    raise ValueError(f"Invalid ticket transition: {ticket.status} -> {status}")
                ticket.status = status
            state = await session.get(SupportTicketAdminState, ticket_id)
            if state is None:
                state = SupportTicketAdminState(ticket_id=ticket_id, priority="normal")
                session.add(state)
            before_priority = state.priority
            if priority:
                state.priority = priority
            await AdminAuditService.record(
                session,
                action="admin.support.updated",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="support_ticket",
                resource_id=str(ticket_id),
                metadata={
                    "status": [before_status, ticket.status],
                    "priority": [before_priority, state.priority],
                },
            )
            return {"id": str(ticket_id), "status": ticket.status, "priority": state.priority}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="support.update",
            target_id=str(ticket_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def reply_ticket(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        ticket_id: uuid.UUID,
        body: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        request: Request | None = None,
        admin_session: AdminSession | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "support.reply", confirmed=confirmed)
        text = body.strip()
        if not text or len(text) > 4000:
            raise ValueError("Support reply must contain 1..4000 characters")
        payload = {"body": text}

        async def operation() -> dict[str, Any]:
            ticket = await session.scalar(
                select(SupportTicket).where(SupportTicket.id == ticket_id).with_for_update()
            )
            if ticket is None:
                raise LookupError("Ticket not found")
            if ticket.status == "closed":
                raise SupportTicketClosedError("Ticket is closed")
            # Order messages at the lock boundary, not at PostgreSQL transaction start.
            now = datetime.now(UTC)
            message = SupportMessage(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                user_id=admin.user_id,
                is_admin=True,
                body=text,
                created_at=now,
            )
            session.add(message)
            ticket.updated_at = now
            if ticket.status == "open":
                ticket.status = "in_progress"
            outbox = SupportOutbox(
                ticket_id=ticket.id,
                message_id=message.id,
                message=message,
                admin_user_id=admin.id,
                status="pending",
            )
            session.add(outbox)
            await session.flush()
            await AdminAuditService.record(
                session,
                action="admin.support.reply_queued",
                outcome="success",
                admin=admin,
                admin_session=admin_session,
                request=request,
                resource_type="support_ticket",
                resource_id=str(ticket.id),
                metadata={"message_id": str(message.id), "outbox_id": str(outbox.id)},
            )
            return {
                "message_id": str(message.id),
                "outbox_id": str(outbox.id),
                "delivery_status": outbox.status,
                "ticket_status": ticket.status,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="support.reply",
            target_id=str(ticket_id),
            request_payload=payload,
            operation=operation,
        )
