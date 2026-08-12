from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import SupportMessage, SupportTicket

router = APIRouter(prefix="/support", tags=["support"])

ACTIVE_USER_STATUSES = {"open", "in_progress"}
REOPENABLE_USER_STATUSES = {"resolved", "closed"}


class CreateTicketRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=8000)


class ReplyTicketRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


def _ticket_view(ticket: SupportTicket) -> dict[str, object]:
    return {
        "id": str(ticket.id),
        "topic": ticket.topic,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "can_reply": ticket.status in ACTIVE_USER_STATUSES,
        "can_close": ticket.status in ACTIVE_USER_STATUSES,
        "can_reopen": ticket.status in REOPENABLE_USER_STATUSES,
    }


async def _owned_ticket(
    session: SessionDep,
    *,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    for_update: bool = False,
) -> SupportTicket:
    statement = select(SupportTicket).where(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    ticket = await session.scalar(statement)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    return ticket


@router.post("/tickets", status_code=201)
async def create_ticket(
    payload: CreateTicketRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    topic = payload.topic.strip()
    message = payload.message.strip()
    if not topic or not message:
        raise HTTPException(status_code=422, detail="Topic and message are required")
    ticket = SupportTicket(user_id=user.id, topic=topic)
    session.add(ticket)
    await session.flush()
    session.add(SupportMessage(ticket_id=ticket.id, user_id=user.id, body=message))
    await session.commit()
    await session.refresh(ticket)
    return _ticket_view(ticket)


@router.get("/tickets")
async def list_tickets(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, object]:
    tickets = list(
        (
            await session.scalars(
                select(SupportTicket)
                .where(SupportTicket.user_id == user.id)
                .order_by(SupportTicket.updated_at.desc(), SupportTicket.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return {
        "items": [_ticket_view(ticket) for ticket in tickets],
        "limit": limit,
        "offset": offset,
    }


@router.get("/tickets/{ticket_id}")
async def ticket_detail(
    ticket_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    ticket = await _owned_ticket(session, ticket_id=ticket_id, user_id=user.id)
    messages = list(
        (
            await session.scalars(
                select(SupportMessage)
                .where(SupportMessage.ticket_id == ticket.id)
                .order_by(SupportMessage.created_at.asc(), SupportMessage.id.asc())
            )
        ).all()
    )
    result = _ticket_view(ticket)
    result["messages"] = [
        {
            "id": str(message.id),
            "body": message.body,
            "author": "support" if message.is_admin else "user",
            "created_at": message.created_at.isoformat(),
        }
        for message in messages
    ]
    return result


@router.post("/tickets/{ticket_id}/messages", status_code=201)
async def reply_ticket(
    ticket_id: uuid.UUID,
    payload: ReplyTicketRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    ticket = await _owned_ticket(
        session,
        ticket_id=ticket_id,
        user_id=user.id,
        for_update=True,
    )
    if ticket.status not in ACTIVE_USER_STATUSES:
        raise HTTPException(status_code=409, detail="Support ticket must be reopened before replying")
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is required")
    row = SupportMessage(ticket_id=ticket.id, user_id=user.id, body=message)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": str(row.id),
        "body": row.body,
        "author": "user",
        "created_at": row.created_at.isoformat(),
    }


@router.post("/tickets/{ticket_id}/close")
async def close_ticket(
    ticket_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    ticket = await _owned_ticket(
        session,
        ticket_id=ticket_id,
        user_id=user.id,
        for_update=True,
    )
    if ticket.status not in ACTIVE_USER_STATUSES:
        raise HTTPException(status_code=409, detail="Support ticket is not active")
    ticket.status = "closed"
    await session.commit()
    await session.refresh(ticket)
    return _ticket_view(ticket)


@router.post("/tickets/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    ticket = await _owned_ticket(
        session,
        ticket_id=ticket_id,
        user_id=user.id,
        for_update=True,
    )
    if ticket.status not in REOPENABLE_USER_STATUSES:
        raise HTTPException(status_code=409, detail="Only resolved or closed support tickets can be reopened")
    ticket.status = "open"
    await session.commit()
    await session.refresh(ticket)
    return _ticket_view(ticket)
