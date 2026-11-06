from __future__ import annotations

import asyncio
import copy
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram.types import User as TelegramUser
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.sql import Select

from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.services.admin_security import AdminAuthService
from app.services.support import SupportConversationService
from app.services.support_recipient_config import (
    SUPPORT_RECIPIENT_SETTING_KEY,
    SupportRecipientConfigService,
)


@pytest_asyncio.fixture
async def bootstrap_actors(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "bootstrap-race-key-at-least-32-characters")
    async with SessionFactory() as session:
        previous = await session.get(AdminRuntimeSetting, SUPPORT_RECIPIENT_SETTING_KEY)
        previous_values = None if previous is None else {
            "value": copy.deepcopy(previous.value),
            "updated_by_admin_id": previous.updated_by_admin_id,
            "created_at": previous.created_at,
            "updated_at": previous.updated_at,
        }
        await session.execute(delete(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == SUPPORT_RECIPIENT_SETTING_KEY,
        ))
        users = [
            User(
                telegram_id=7_900_000_000_000 + uuid.uuid4().int % 100_000_000_000,
                first_name=f"Bootstrap race actor {number}",
            )
            for number in range(3)
        ]
        session.add_all(users)
        await session.flush()
        owner = AdminAccount(user_id=users[2].id, role="owner", is_active=True)
        session.add(owner)
        await session.commit()
    monkeypatch.setattr(
        settings, "admin_bootstrap_telegram_ids",
        ",".join(str(user.telegram_id) for user in users[:2]),
    )
    try:
        yield SimpleNamespace(candidates=users[:2], third_user=users[2], owner=owner)
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(AdminRuntimeSetting).where(
                AdminRuntimeSetting.key == SUPPORT_RECIPIENT_SETTING_KEY,
            ))
            if previous_values is not None:
                session.add(AdminRuntimeSetting(
                    key=SUPPORT_RECIPIENT_SETTING_KEY, **previous_values,
                ))
            await session.execute(delete(AdminAccount).where(
                AdminAccount.user_id.in_([user.id for user in users]),
            ))
            await session.execute(delete(User).where(User.id.in_([user.id for user in users])))
            await session.commit()


@asynccontextmanager
async def _first_enrollments(monkeypatch, actors, *, pause_loser=False):
    original_policy = SupportRecipientConfigService.policy
    both_absent = asyncio.Event()
    both_snapshots = asyncio.Event()
    enrollment_sessions = set()
    absent_sessions = set()
    snapshot_sessions = set()
    race = SimpleNamespace(
        conflict=asyncio.Event(), release=asyncio.Event(), loser_user_id=None, tasks=[],
    )

    async def synchronized_policy(session, *, lock=False, for_update=False):
        row = await original_policy(session, lock=lock, for_update=for_update)
        if (
            session in enrollment_sessions and session not in absent_sessions
            and not lock and not for_update and row is None
        ):
            absent_sessions.add(session)
            if len(absent_sessions) == 2:
                both_absent.set()
            await asyncio.wait_for(both_absent.wait(), timeout=5)
        return row

    monkeypatch.setattr(
        SupportRecipientConfigService, "policy", staticmethod(synchronized_policy),
    )

    async def enroll(user):
        async with SessionFactory() as session:
            enrollment_sessions.add(session)
            original_execute = session.execute

            async def synchronized_execute(statement, *args, **kwargs):
                result = await original_execute(statement, *args, **kwargs)
                if (
                    isinstance(statement, Select)
                    and session not in snapshot_sessions
                    and {item.get("entity") for item in statement.column_descriptions}
                    == {User, AdminAccount}
                ):
                    # Both accounts are uncommitted: each actual SELECT sees only its own.
                    snapshot_sessions.add(session)
                    if len(snapshot_sessions) == 2:
                        both_snapshots.set()
                    await asyncio.wait_for(both_snapshots.wait(), timeout=5)
                if (
                    pause_loser and isinstance(statement, Insert)
                    and statement.table.name == AdminRuntimeSetting.__tablename__
                    and result.rowcount == 0
                ):
                    race.loser_user_id = user.id
                    race.conflict.set()
                    await asyncio.wait_for(race.release.wait(), timeout=5)
                return result

            monkeypatch.setattr(session, "execute", synchronized_execute)
            account = await AdminAuthService.get_or_bootstrap_admin(session, TelegramUser(
                id=user.telegram_id, first_name=user.first_name, is_bot=False,
            ))
            assert account is not None
            await session.commit()
            return account.id

    race.tasks = [asyncio.create_task(enroll(user)) for user in actors.candidates]
    try:
        yield race
    finally:
        race.release.set()
        try:
            await asyncio.wait_for(
                asyncio.gather(*race.tasks, return_exceptions=True), timeout=8,
            )
        except TimeoutError:
            for task in race.tasks:
                task.cancel()
            await asyncio.gather(*race.tasks, return_exceptions=True)


async def _policy_ids():
    async with SessionFactory() as session:
        policy = await SupportRecipientConfigService.policy(session)
        assert policy is not None
        return SupportRecipientConfigService.admin_ids(policy)


async def _owner_save(actors, target_id, enabled):
    async with SessionFactory() as session:
        owner = await session.get(AdminAccount, actors.owner.id)
        policy = await SupportRecipientConfigService.prepare_change(
            session, admin=owner, initialize=True,
        )
        account = await session.scalar(select(AdminAccount).where(
            AdminAccount.id == target_id,
        ).with_for_update())
        user = await session.get(User, account.user_id)
        await SupportRecipientConfigService.set_subscription(
            session, policy=policy, admin=owner, account=account, user=user, enabled=enabled,
        )
        await session.commit()


@pytest.mark.asyncio
async def test_concurrent_first_bootstrap_snapshots_both_persist(monkeypatch, bootstrap_actors):
    actors = bootstrap_actors
    async with _first_enrollments(monkeypatch, actors) as race:
        account_ids = set(await asyncio.wait_for(asyncio.gather(*race.tasks), timeout=8))

    assert await _policy_ids() == account_ids
    assert actors.owner.id not in account_ids
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    async with SessionFactory() as session:
        for user in actors.candidates:
            assert await SupportConversationService.authorized_operator(
                session, user.id, lock=True,
            )

    # A subsequent enrollment/ENV expansion is not another initialization.
    monkeypatch.setattr(
        settings, "admin_bootstrap_telegram_ids", str(actors.third_user.telegram_id),
    )
    async with SessionFactory() as session:
        await SupportRecipientConfigService.seed_from_bootstrap(session)
        await session.commit()
    assert await _policy_ids() == account_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_choice", ["empty", "unchanged_true", "unchanged_false"])
async def test_owner_save_wins_over_waiting_bootstrap_initializer(
    monkeypatch, bootstrap_actors, owner_choice,
):
    actors = bootstrap_actors
    async with _first_enrollments(monkeypatch, actors, pause_loser=True) as race:
        await asyncio.wait_for(race.conflict.wait(), timeout=5)
        before = await _policy_ids()
        assert len(before) == 1
        winner_id = next(iter(before))
        if owner_choice == "unchanged_false":
            await _owner_save(actors, actors.owner.id, False)
        else:
            await _owner_save(actors, winner_id, owner_choice == "unchanged_true")
        race.release.set()
        await asyncio.wait_for(asyncio.gather(*race.tasks), timeout=8)

    assert await _policy_ids() == (set() if owner_choice == "empty" else before)


@pytest.mark.asyncio
async def test_losing_initializer_rechecks_current_user_activity(monkeypatch, bootstrap_actors):
    actors = bootstrap_actors
    async with _first_enrollments(monkeypatch, actors, pause_loser=True) as race:
        await asyncio.wait_for(race.conflict.wait(), timeout=5)
        before = await _policy_ids()
        assert len(before) == 1
        async with SessionFactory() as session:
            await session.execute(update(User).where(
                User.id == race.loser_user_id,
            ).values(is_active=False))
            await session.commit()
        race.release.set()
        await asyncio.wait_for(asyncio.gather(*race.tasks), timeout=8)

    assert await _policy_ids() == before
    async with SessionFactory() as session:
        assert not await SupportConversationService.authorized_operator(
            session, race.loser_user_id, lock=True,
        )
