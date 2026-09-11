from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import AdminAccount, User
from app.services import creator_partnership as creator_module
from app.services.creator_partnership import CreatorPartnershipService


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _statement):
        return _Rows(self._rows)


def _user(*, telegram_id: int, username: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        telegram_id=telegram_id,
        username=username,
        first_name="Test",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_bootstrap_admin_alert_uses_durable_notification_outbox(monkeypatch) -> None:
    applicant = _user(telegram_id=9001, username="creator")
    active_admin = _user(telegram_id=9101)
    bootstrap_without_row = _user(telegram_id=9102)
    revoked_admin = _user(telegram_id=9103)

    active_account = AdminAccount(
        id=uuid.uuid4(),
        user_id=active_admin.id,
        role="owner",
        is_active=True,
    )
    revoked_account = AdminAccount(
        id=uuid.uuid4(),
        user_id=revoked_admin.id,
        role="owner",
        is_active=False,
    )
    session = _Session(
        [
            (active_admin, active_account),
            (bootstrap_without_row, None),
            (revoked_admin, revoked_account),
        ]
    )
    application = SimpleNamespace(
        id=uuid.uuid4(),
        channel_name="Instagram",
        channel_url="https://instagram.com/creator",
        audience_size=12_345,
        average_views=6_789,
        cooperation_format="Обзоры",
        message="Делаю генерации в ROXY и зову аудиторию повторять их.",
        created_at=datetime(2026, 9, 9, 9, 9, 28, tzinfo=UTC),
    )

    monkeypatch.setattr(creator_module, "parse_bootstrap_ids", lambda: {9101, 9102, 9103})
    create = AsyncMock()
    monkeypatch.setattr(creator_module.NotificationService, "create", create)

    await CreatorPartnershipService._notify_bootstrap_admins(
        session,  # type: ignore[arg-type]
        applicant=applicant,
        application=application,  # type: ignore[arg-type]
    )

    assert create.await_count == 2
    recipients = {call.kwargs["user_id"] for call in create.await_args_list}
    assert recipients == {active_admin.id, bootstrap_without_row.id}
    for call in create.await_args_list:
        assert call.kwargs["kind"] == "creator_partnership_admin_application"
        assert call.kwargs["title"] == "Новая заявка на партнёрство"
        body = call.kwargs["body"]
        assert "@creator" in body
        assert "Аудитория: 12 345" in body
        assert "Средние просмотры: 6 789" in body
        assert "✅ ОДОБРИТЬ" in body
        assert "❌ ОТКЛОНИТЬ" in body
        assert "⏳ ОСТАВИТЬ НА РАССМОТРЕНИИ" in body
        assert "Ссылка: https://instagram.com/creator" in body
        assert f"Application ID: {application.id}" in body

    # The service only creates durable notification rows. It has no Bot API
    # dependency in the request path, so Telegram downtime is handled later by
    # the retry-capable notification worker instead of failing the application.
    assert "aiogram" not in creator_module.__dict__
