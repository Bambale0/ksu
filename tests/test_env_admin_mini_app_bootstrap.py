from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.db.models import AdminAccount
from app.services.billing_access import BillingAccessService
from app.services.inline_admin import ensure_bootstrap_admin


class _FakeSession:
    def __init__(self, existing: AdminAccount | None = None) -> None:
        self.existing = existing
        self.executed = 0
        self.added = 0
        self.flushed = 0

    async def execute(self, _statement):  # type: ignore[no-untyped-def]
        self.executed += 1
        return None

    async def scalar(self, _statement):  # type: ignore[no-untyped-def]
        return self.existing

    def add(self, account: AdminAccount) -> None:
        self.added += 1
        self.existing = account

    async def flush(self) -> None:
        self.flushed += 1


@pytest.mark.asyncio
async def test_env_admin_is_materialized_for_signed_mini_app_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "1001, 2002")
    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=2002, is_active=True)
    session = _FakeSession()

    account = await ensure_bootstrap_admin(session, user)  # type: ignore[arg-type]

    assert account is not None
    assert account.user_id == user.id
    assert account.role == "owner"
    assert account.is_active is True
    assert session.executed == 1
    assert session.added == 1
    assert session.flushed == 1
    assert await BillingAccessService.is_active_admin(session, user.id) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_non_env_user_never_touches_admin_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "1001")
    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=2002, is_active=True)
    session = _FakeSession()

    account = await ensure_bootstrap_admin(session, user)  # type: ignore[arg-type]

    assert account is None
    assert session.executed == 0
    assert session.added == 0
    assert session.flushed == 0


@pytest.mark.asyncio
async def test_restricted_env_user_is_never_bootstrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "2002")
    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=2002, is_active=False)
    session = _FakeSession()

    account = await ensure_bootstrap_admin(session, user)  # type: ignore[arg-type]

    assert account is None
    assert session.executed == 0
    assert session.added == 0
    assert session.flushed == 0


@pytest.mark.asyncio
async def test_env_bootstrap_does_not_reactivate_revoked_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "2002")
    user_id = uuid.uuid4()
    revoked = AdminAccount(user_id=user_id, role="owner", is_active=False)
    user = SimpleNamespace(id=user_id, telegram_id=2002, is_active=True)
    session = _FakeSession(existing=revoked)

    account = await ensure_bootstrap_admin(session, user)  # type: ignore[arg-type]

    assert account is revoked
    assert account.is_active is False
    assert session.executed == 0
    assert session.added == 0
    assert session.flushed == 0


def test_env_admin_bootstrap_runs_only_after_signed_identity_resolution() -> None:
    source = Path("app/api/deps.py").read_text(encoding="utf-8")

    signature_check = source.index("safe_parse_webapp_init_data(settings.bot_token")
    user_resolution = source.index("user = await UserService.get_or_create")
    admin_bootstrap = source.index("await ensure_bootstrap_admin(session, user)")
    commit = source.index("await session.commit()", admin_bootstrap)

    assert signature_check < user_resolution < admin_bootstrap < commit
