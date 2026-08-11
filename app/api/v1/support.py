from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.db.models import SupportMessage, SupportTicket

router = APIRouter(prefix="/support", tags=["support"])


class CreateTicketRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=8000)


@router.post("/tickets", status_code=201)
async def create_ticket(
    payload: CreateTicketRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    ticket = SupportTicket(user_id=user.id, topic=payload.topic)
    session.add(ticket)
    await session.flush()
    session.add(SupportMessage(ticket_id=ticket.id, user_id=user.id, body=payload.message))
    await session.commit()
    return {"id": str(ticket.id), "status": ticket.status}


@router.get("/tickets")
async def list_tickets(user: CurrentUserDep, session: SessionDep) -> list[dict[str, object]]:
    tickets = (
        await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id)
            .order_by(SupportTicket.created_at.desc())
        )
    ).all()
    return [
        {
            "id": str(ticket.id),
            "topic": ticket.topic,
            "status": ticket.status,
            "created_at": ticket.created_at,
        }
        for ticket in tickets
    ]
