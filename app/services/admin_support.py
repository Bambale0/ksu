from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import SupportOutbox, SupportTicketAdminState
from app.db.models import AdminAccount, AdminSession, SupportMessage, SupportTicket
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.admin_security import AdminAuditService

SupportStatus = Literal["open", "in_progress", "resolved", "closed"]
SupportPriority = Literal["low", "normal", "high", "urgent"]


class AdminSupportService:
    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "support.read")
        stmt = (
            select(SupportTicket, SupportTicketAdminState)
            .outerjoin(
                SupportTicketAdminState,
                SupportTicketAdminState.ticket_id == SupportTicket.id,
            )
        )
        if status:
            stmt = stmt.where(SupportTicket.status == status)
        rows = (
            await session.execute(
                stmt.order_by(SupportTicket.updated_at.desc())
                .offset(max(0, min(offset, 100_000)))
                .limit(max(1, min(limit, 100)))
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(ticket.id),
                    "user_id": str(ticket.user_id),
                    "topic": ticket.topic,
                    "status": ticket.status,
                    "assigned_admin_id": (
                        str(state.assigned_admin_id) if state and state.assigned_admin_id else None
                    ),
                    "priority": state.priority if state else "normal",
                    "created_at": ticket.created_at.isoformat(),
                    "updated_at": ticket.updated_at.isoformat(),
                }
                for ticket, state in rows
            ]
        }

    @staticmethod
    async def get_ticket(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        ticket_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "support.read")
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")
        state = await session.get(SupportTicketAdminState, ticket_id)
        messages = list(
            (
                await session.scalars(
                    select(SupportMessage)
                    .where(SupportMessage.ticket_id == ticket_id)
                    .order_by(SupportMessage.created_at.asc())
                    .limit(500)
                )
            ).all()
        )
        return {
            "id": str(ticket.id),
            "user_id": str(ticket.user_id),
            "topic": ticket.topic,
            "status": ticket.status,
            "assigned_admin_id": (
                str(state.assigned_admin_id) if state and state.assigned_admin_id else None
            ),
            "priority": state.priority if state else "normal",
            "messages": [
                {
                    "id": str(message.id),
                    "sender_user_id": str(message.user_id) if message.user_id else None,
                    "is_admin": message.is_admin,
                    "body": message.body,
                    "created_at": message.created_at.isoformat(),
                }
                for message in messages
            ],
        }

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
                raise ValueError("Ticket is closed")
            message = SupportMessage(
                ticket_id=ticket.id,
                user_id=admin.user_id,
                is_admin=True,
                body=text,
            )
            session.add(message)
            if ticket.status == "open":
                ticket.status = "in_progress"
            await session.flush()
            outbox = SupportOutbox(
                ticket_id=ticket.id,
                message_id=message.id,
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
