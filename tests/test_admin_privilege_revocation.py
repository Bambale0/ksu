import random
import uuid

import pytest

from app.core.config import settings
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.services.admin_users import AdminUserService


@pytest.fixture(autouse=True)
def _configured_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "a" * 64)


@pytest.mark.asyncio
async def test_blocking_linked_admin_user_revokes_admin_account() -> None:
    async with SessionFactory() as session:
        owner_user = User(
            telegram_id=random.randint(8_500_000_000_000, 8_599_999_999_999),
            first_name="Owner revoke test",
        )
        target_user = User(
            telegram_id=random.randint(8_600_000_000_000, 8_699_999_999_999),
            first_name="Admin revoke test",
        )
        session.add_all([owner_user, target_user])
        await session.flush()
        owner = AdminAccount(
            user_id=owner_user.id,
            role="owner",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        target_admin = AdminAccount(
            user_id=target_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        session.add_all([owner, target_admin])
        await session.flush()
        target_admin_id = target_admin.id
        target_user_id = target_user.id

        result, replayed = await AdminUserService.set_blocked(
            session,
            admin=owner,
            user_id=target_user_id,
            blocked=True,
            reason="integration privilege revocation",
            idempotency_key=f"integration-admin-revoke:{uuid.uuid4()}",
            request_id="integration-admin-revoke",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()

        assert replayed is False
        assert result["is_active"] is False
        session.expire_all()
        refreshed_admin = await session.get(AdminAccount, target_admin_id)
        assert refreshed_admin is not None
        assert refreshed_admin.is_active is False
