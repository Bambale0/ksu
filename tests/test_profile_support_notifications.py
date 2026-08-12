from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.me import UpdatePreferenceRequest, preferences, update_preferences
from app.api.v1.notifications import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.api.v1.support import (
    CreateTicketRequest,
    ReplyTicketRequest,
    close_ticket,
    create_ticket,
    reopen_ticket,
    reply_ticket,
    ticket_detail,
)
from app.db.models import Notification, SupportMessage, SupportTicket, User
from app.db.session import SessionFactory

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


@pytest.mark.asyncio
async def test_profile_preferences_are_durable_and_server_validated() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=930000000000001, first_name="Profile")
        session.add(user)
        await session.commit()

        current = await preferences(user, session)
        assert current == {
            "ui_language": "auto",
            "notifications_enabled": True,
            "marketing_notifications": False,
            "profile_discoverable": False,
        }

        updated = await update_preferences(
            UpdatePreferenceRequest(
                ui_language="en",
                notifications_enabled=True,
                marketing_notifications=True,
                profile_discoverable=True,
            ),
            user,
            session,
        )
        assert updated["ui_language"] == "en"
        assert updated["marketing_notifications"] is True
        assert updated["profile_discoverable"] is True

        with pytest.raises(HTTPException) as error:
            await update_preferences(
                UpdatePreferenceRequest(ui_language="unsupported"),
                user,
                session,
            )
        assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_notification_inbox_is_owner_scoped_and_read_state_is_authoritative() -> None:
    async with SessionFactory() as session:
        owner = User(telegram_id=930000000000002, first_name="Owner")
        other = User(telegram_id=930000000000003, first_name="Other")
        session.add_all([owner, other])
        await session.flush()
        owner_id = owner.id
        other_id = other.id

        first = Notification(
            user_id=owner_id,
            kind="generation",
            title="Готово",
            body="Первая генерация завершена",
        )
        second = Notification(
            user_id=owner_id,
            kind="system",
            title="Система",
            body="Второе уведомление",
        )
        foreign = Notification(
            user_id=other_id,
            kind="system",
            title="Чужое",
            body="Не должно быть доступно",
        )
        session.add_all([first, second, foreign])
        await session.commit()
        first_id = first.id
        foreign_id = foreign.id

        payload = await list_notifications(
            owner,
            session,
            unread_only=False,
            limit=50,
            offset=0,
        )
        assert payload["unread_count"] == 2
        assert {item["id"] for item in payload["items"]} == {str(first.id), str(second.id)}

        await mark_notification_read(first_id, owner, session)
        payload = await list_notifications(
            owner,
            session,
            unread_only=True,
            limit=50,
            offset=0,
        )
        assert payload["unread_count"] == 1
        assert [item["id"] for item in payload["items"]] == [str(second.id)]

        with pytest.raises(HTTPException) as error:
            await mark_notification_read(foreign_id, owner, session)
        assert error.value.status_code == 404

        result = await mark_all_notifications_read(owner, session)
        assert result["updated"] == 1
        foreign_row = await session.get(Notification, foreign_id)
        assert foreign_row is not None
        assert foreign_row.is_read is False


@pytest.mark.asyncio
async def test_support_thread_stays_replyable_after_admin_moves_it_in_progress() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=930000000000004, first_name="Support user")
        stranger = User(telegram_id=930000000000005, first_name="Stranger")
        session.add_all([user, stranger])
        await session.commit()

        created = await create_ticket(
            CreateTicketRequest(topic="Оплата", message="Не вижу пополнение"),
            user,
            session,
        )
        ticket_id = uuid.UUID(str(created["id"]))

        ticket = await session.get(SupportTicket, ticket_id)
        assert ticket is not None
        ticket.status = "in_progress"
        session.add(
            SupportMessage(
                ticket_id=ticket_id,
                user_id=None,
                is_admin=True,
                body="Проверяем платёж, пришлите детали.",
            )
        )
        await session.commit()

        detail = await ticket_detail(ticket_id, user, session)
        assert detail["status"] == "in_progress"
        assert detail["can_reply"] is True
        assert detail["can_close"] is True
        assert any(item["author"] == "support" for item in detail["messages"])

        reply = await reply_ticket(
            ticket_id,
            ReplyTicketRequest(message="Вот ID операции"),
            user,
            session,
        )
        assert reply["author"] == "user"

        closed = await close_ticket(ticket_id, user, session)
        assert closed["status"] == "closed"
        assert closed["can_reopen"] is True

        with pytest.raises(HTTPException) as error:
            await reply_ticket(
                ticket_id,
                ReplyTicketRequest(message="Нельзя до reopen"),
                user,
                session,
            )
        assert error.value.status_code == 409

        reopened = await reopen_ticket(ticket_id, user, session)
        assert reopened["status"] == "open"
        assert reopened["can_reply"] is True

        ticket = await session.get(SupportTicket, ticket_id)
        assert ticket is not None
        ticket.status = "resolved"
        await session.commit()
        reopened_resolved = await reopen_ticket(ticket_id, user, session)
        assert reopened_resolved["status"] == "open"

        with pytest.raises(HTTPException) as ownership_error:
            await ticket_detail(ticket_id, stranger, session)
        assert ownership_error.value.status_code == 404

        messages = list(
            (
                await session.scalars(
                    select(SupportMessage)
                    .where(SupportMessage.ticket_id == ticket_id)
                    .order_by(SupportMessage.created_at.asc())
                )
            ).all()
        )
        assert len(messages) == 3


def test_profile_tools_use_signed_telegram_auth_and_no_browser_business_state() -> None:
    script = (MINI / "profile-tools.js").read_text(encoding="utf-8")
    for token in (
        '"/api/v1/me/preferences"',
        '"/api/v1/notifications?limit=50"',
        '"/api/v1/notifications/read-all"',
        '"/api/v1/support/tickets?limit=50"',
        'headers["X-Telegram-Init-Data"] = tg.initData',
        'method: "PUT"',
        'method: "POST"',
        "state.unreadCount",
        "ticket.can_reopen",
        "ticket.can_reply",
    ):
        assert token in script, token
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "initDataUnsafe" not in script


def test_profile_tools_mount_inside_existing_profile_and_ci_checks_js() -> None:
    integration = (MINI / "shell-integration.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'document.getElementById("profileView")' in integration
    assert 'stylesheet.href = "/mini-app/profile-tools.css"' in integration
    assert 'script.src = "/mini-app/profile-tools.js"' in integration
    assert "node --check app/web/mini_app/profile-tools.js" in workflow
    assert (MINI / "profile-tools.css").is_file()
