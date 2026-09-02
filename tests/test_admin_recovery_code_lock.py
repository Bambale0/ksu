import random

import pytest

from app.api.v1.admin_auth import _lock_admin_for_recovery_code
from app.core.config import settings
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.services.admin_security import consume_recovery_code, hash_recovery_code


@pytest.mark.asyncio
async def test_admin_recovery_code_lock_refreshes_stale_identity_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "r" * 64)
    recovery_code = "abcd1234-ef567890"

    async with SessionFactory() as setup_session:
        user = User(
            telegram_id=random.randint(400_000_000_000, 499_999_999_999),
            first_name="RecoveryLockCI",
        )
        setup_session.add(user)
        await setup_session.flush()
        admin = AdminAccount(
            user_id=user.id,
            role="owner",
            is_active=True,
            recovery_code_hashes=[hash_recovery_code(recovery_code)],
        )
        setup_session.add(admin)
        await setup_session.flush()
        admin_id = admin.id
        await setup_session.commit()

    async with SessionFactory() as stale_session:
        stale_admin = await stale_session.get(AdminAccount, admin_id)
        assert stale_admin is not None
        assert stale_admin.recovery_code_hashes == [hash_recovery_code(recovery_code)]

        async with SessionFactory() as writer_session:
            locked_admin = await _lock_admin_for_recovery_code(writer_session, admin_id)
            assert consume_recovery_code(locked_admin, recovery_code)
            await writer_session.commit()

        refreshed_admin = await _lock_admin_for_recovery_code(stale_session, admin_id)
        assert refreshed_admin is stale_admin
        assert refreshed_admin.recovery_code_hashes == []
        assert not consume_recovery_code(refreshed_admin, recovery_code)
        await stale_session.rollback()
