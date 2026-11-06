from __future__ import annotations

import asyncio
import copy
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete

from app.api.v1 import me, notifications
from app.core.config import settings
from app.core.telegram_browser_auth import build_browser_init_data
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, Notification, User
from app.db.session import SessionFactory
from app.services.support import SupportConversationService

SETTING_KEY = "support_incoming_recipients"
BOT_TOKEN = "123456:isolated-private-notification-lock-test"


@pytest_asyncio.fixture
async def selected_owner(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    async with SessionFactory() as session:
        owner = User(
            telegram_id=7_700_000_000_000 + uuid.uuid4().int % 100_000_000_000,
            first_name="Private read concurrency",
        )
        session.add(owner)
        await session.flush()
        account = AdminAccount(user_id=owner.id, role="owner", is_active=True)
        session.add(account)
        await session.flush()
        policy = await session.get(AdminRuntimeSetting, SETTING_KEY)
        previous = None if policy is None else (
            copy.deepcopy(policy.value), policy.updated_by_admin_id,
        )
        if policy is None:
            policy = AdminRuntimeSetting(key=SETTING_KEY)
            session.add(policy)
        policy.value = {"revision": 1, "admin_ids": [str(account.id)], "source": "owner"}
        policy.updated_by_admin_id = account.id
        session.add_all([
            Notification(
                user_id=owner.id, kind="support_incoming", title="Support notice",
                body="Synthetic support notice", is_read=False,
            ),
            Notification(
                user_id=owner.id, kind="neironych_balance_low", title="Balance notice",
                body="Synthetic private balance notice", is_read=False,
            ),
        ])
        await session.commit()
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner.telegram_id))
    try:
        yield owner
    finally:
        async with SessionFactory() as session:
            if previous is None:
                await session.execute(delete(AdminRuntimeSetting).where(
                    AdminRuntimeSetting.key == SETTING_KEY,
                ))
            else:
                policy = await session.get(AdminRuntimeSetting, SETTING_KEY)
                policy.value, policy.updated_by_admin_id = previous
            await session.commit()


@pytest.mark.asyncio
async def test_parallel_authenticated_inbox_and_profile_do_not_upgrade_shared_owner_locks(
    monkeypatch, selected_owner,
):
    owner = selected_owner
    original = SupportConversationService.authorized_operator
    both_readers = asyncio.Event()
    arrivals = 0

    async def synchronize_after_support_authorization(session, user_id, *, lock=False):
        nonlocal arrivals
        allowed = await original(session, user_id, lock=lock)
        assert allowed and lock
        arrivals += 1
        if arrivals == 2:
            both_readers.set()
        await asyncio.wait_for(both_readers.wait(), timeout=4)
        return allowed

    monkeypatch.setattr(
        SupportConversationService, "authorized_operator",
        staticmethod(synchronize_after_support_authorization),
    )
    app = FastAPI()
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    headers = {"X-Telegram-Init-Data": build_browser_init_data(
        {"id": owner.telegram_id, "first_name": owner.first_name}, BOT_TOKEN,
    )}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers,
    ) as client:
        results = await asyncio.wait_for(asyncio.gather(
            client.get("/api/v1/notifications"),
            client.get("/api/v1/me/overview"),
            return_exceptions=True,
        ), timeout=8)
    outcomes = [
        item.status_code if isinstance(item, httpx.Response) else type(item).__name__
        for item in results
    ]
    assert outcomes == [200, 200], f"Concurrent private reads failed: {outcomes}"
    assert arrivals == 2
    assert {item["kind"] for item in results[0].json()["items"]} == {
        "support_incoming", "neironych_balance_low",
    }
    assert results[1].json()["notifications"]["unread"] == 2
