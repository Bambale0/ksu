from __future__ import annotations

import asyncio
import copy
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User as TelegramUser
from fastapi import FastAPI
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1 import support as support_api
from app.bot.handlers import support as bot_support
from app.bot.middlewares import DatabaseSessionMiddleware
from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, Notification, SupportMessage, SupportTicket, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.main import resource_policy_error
from app.services.abuse_protection import ResourcePolicyError
from app.services.notification_events import register_notification_events
from app.services.notifications import NotificationService

SETTING_KEY = "support_incoming_recipients"


@pytest_asyncio.fixture
async def actors(monkeypatch):
    monkeypatch.setattr(settings, "support_telegram_url", "")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "abuse_fail_closed", True)
    monkeypatch.setattr(settings, "support_message_rate_limit_per_minute", 10)
    register_notification_events()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    async with SessionFactory() as session:
        customer, operator = [
            User(
                telegram_id=7_500_000_000_000 + uuid.uuid4().int % 100_000_000_000,
                first_name=f"Legacy support {kind}",
            )
            for kind in ("customer", "operator")
        ]
        session.add_all([customer, operator])
        await session.flush()
        account = AdminAccount(user_id=operator.id, role="support", is_active=True)
        session.add(account)
        await session.flush()
        previous = await session.get(AdminRuntimeSetting, SETTING_KEY)
        previous_values = None if previous is None else {
            "value": copy.deepcopy(previous.value),
            "updated_by_admin_id": previous.updated_by_admin_id,
        }
        if previous is None:
            previous = AdminRuntimeSetting(key=SETTING_KEY)
            session.add(previous)
        previous.value = {"revision": 1, "admin_ids": [str(account.id)], "source": "owner"}
        previous.updated_by_admin_id = account.id
        await session.commit()
    result = SimpleNamespace(
        customer=customer, operator=operator, account=account, redis=redis,
    )
    try:
        yield result
    finally:
        await redis.delete(f"abuse:support:user:{customer.id}")
        await redis.aclose()
        async with SessionFactory() as session:
            notices = select(Notification.id).where(Notification.user_id == operator.id)
            await session.execute(delete(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_(notices),
            ))
            await session.execute(delete(Notification).where(Notification.user_id == operator.id))
            tickets = select(SupportTicket.id).where(SupportTicket.user_id == customer.id)
            await session.execute(delete(SupportMessage).where(SupportMessage.ticket_id.in_(tickets)))
            await session.execute(delete(SupportTicket).where(SupportTicket.user_id == customer.id))
            if previous_values is None:
                await session.execute(delete(AdminRuntimeSetting).where(AdminRuntimeSetting.key == SETTING_KEY))
            else:
                policy = await session.get(AdminRuntimeSetting, SETTING_KEY)
                policy.value = previous_values["value"]
                policy.updated_by_admin_id = previous_values["updated_by_admin_id"]
            await session.execute(delete(AdminAccount).where(AdminAccount.id == account.id))
            await session.execute(delete(User).where(User.id.in_([customer.id, operator.id])))
            await session.commit()


async def _waiting_state(actors):
    state = FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=123456, chat_id=actors.customer.telegram_id, user_id=actors.customer.telegram_id),
    )
    await state.set_state(bot_support.SupportFlow.waiting_message)
    await state.update_data(topic="Legacy conversation")
    return state


def _message(actors, *, body=" Private customer issue ", answer=None):
    return SimpleNamespace(
        message_id=uuid.uuid4().int % 2**31,
        bot=SimpleNamespace(id=123456),
        chat=SimpleNamespace(id=actors.customer.telegram_id, type="private"),
        from_user=TelegramUser(
            id=actors.customer.telegram_id, first_name=actors.customer.first_name, is_bot=False,
        ),
        text=body,
        answer=answer or AsyncMock(),
    )


async def _invoke(actors, state, message, *, backend=None):
    async def dispatch(event, data):
        # Exercise aiogram's real signature-based DI; the old handler ignores redis.
        return await HandlerObject(callback=bot_support.support_message).call(
            message=event, state=state, session=data["session"],
            redis=backend if backend is not None else actors.redis,
        )

    await DatabaseSessionMiddleware()(
        dispatch, message, {"event_from_user": message.from_user},
    )


async def _counts(actors):
    async with SessionFactory() as session:
        tickets = select(SupportTicket.id).where(SupportTicket.user_id == actors.customer.id)
        notices = select(Notification.id).where(Notification.user_id == actors.operator.id)
        return (
            await session.scalar(select(func.count()).select_from(SupportTicket).where(
                SupportTicket.user_id == actors.customer.id,
            )),
            await session.scalar(select(func.count()).select_from(SupportMessage).where(
                SupportMessage.ticket_id.in_(tickets),
            )),
            await session.scalar(select(func.count()).select_from(Notification).where(
                Notification.user_id == actors.operator.id,
            )),
            await session.scalar(select(func.count()).select_from(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_(notices),
            )),
        )


@asynccontextmanager
async def _api_client(actors):
    app = FastAPI()
    app.state.redis = actors.redis
    app.include_router(support_api.router, prefix="/api/v1")
    app.add_exception_handler(ResourcePolicyError, resource_policy_error)

    async def current_user():
        return actors.customer

    app.dependency_overrides[get_current_user] = current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [" Private customer issue ", None])
async def test_legacy_handler_uses_canonical_message_activity_and_operator_delivery(actors, body):
    state = await _waiting_state(actors)
    message = _message(actors, body=body)
    await _invoke(actors, state, message)

    assert await _counts(actors) == (1, 1, 1, 1)
    assert await state.get_state() is None
    async with SessionFactory() as session:
        ticket = await session.scalar(select(SupportTicket).where(
            SupportTicket.user_id == actors.customer.id,
        ))
        stored = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
        notice = await session.scalar(select(Notification).where(
            Notification.user_id == actors.operator.id,
        ))
        assert stored.body == (body.strip() if body else "[не текстовое сообщение]")
        assert ticket.updated_at == stored.created_at
        assert notice.kind == "support_incoming"
        assert str(ticket.id) in notice.body
        assert stored.body not in notice.body
        assert str(ticket.id) in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_success_acknowledgement_observes_committed_ticket_message_and_notice(actors):
    state = await _waiting_state(actors)

    async def acknowledge(text, **_kwargs):
        assert text.startswith("✅")
        assert await _counts(actors) == (1, 1, 1, 1)

    await _invoke(actors, state, _message(actors, answer=AsyncMock(side_effect=acknowledge)))
    assert await state.get_state() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["enqueue", "commit"])
async def test_persistence_failure_rolls_back_conversation_and_retains_fsm(actors, monkeypatch, failure):
    state = await _waiting_state(actors)
    message = _message(actors)
    if failure == "enqueue":
        monkeypatch.setattr(
            NotificationService, "enqueue_existing", AsyncMock(side_effect=RuntimeError("Synthetic enqueue failure")),
        )
        expected = RuntimeError
    else:
        original = AsyncSession.commit
        injected = False

        async def fail_support_commit(session):
            nonlocal injected
            count = await session.scalar(select(func.count()).select_from(SupportTicket).where(
                SupportTicket.user_id == actors.customer.id,
            ))
            if count and not injected:
                injected = True
                raise SQLAlchemyError("Synthetic commit failure")
            return await original(session)

        monkeypatch.setattr(AsyncSession, "commit", fail_support_commit)
        expected = SQLAlchemyError

    with pytest.raises(expected):
        await _invoke(actors, state, message)
    assert await _counts(actors) == (0, 0, 0, 0)
    assert await state.get_state() == bot_support.SupportFlow.waiting_message.state
    assert (await state.get_data())["topic"] == "Legacy conversation"
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["api", "bot"])
async def test_bot_and_api_share_one_customer_message_budget(actors, monkeypatch, first):
    monkeypatch.setattr(settings, "support_message_rate_limit_per_minute", 1)
    state = await _waiting_state(actors)
    message = _message(actors)
    async with _api_client(actors) as client:
        payload = {"topic": "Shared quota", "message": "API message"}
        if first == "api":
            assert (await client.post("/api/v1/support/tickets", json=payload)).status_code == 201
            await _invoke(actors, state, message)
            assert await state.get_state() == bot_support.SupportFlow.waiting_message.state
            assert (await state.get_data())["topic"] == "Legacy conversation"
            assert message.answer.await_count == 1
            assert not message.answer.await_args.args[0].startswith("✅")
            assert "сек" in message.answer.await_args.args[0]
        else:
            await _invoke(actors, state, message)
            limited = await client.post("/api/v1/support/tickets", json=payload)
            assert limited.status_code == 429, limited.text
            assert int(limited.headers["Retry-After"]) > 0
    assert await _counts(actors) == (1, 1, 1, 1)


class BrokenRedis:
    async def eval(self, *_args, **_kwargs):
        raise RedisError("Synthetic quota backend unavailable")


@pytest.mark.asyncio
async def test_unavailable_quota_backend_retains_waiting_state_without_persistence(actors):
    state = await _waiting_state(actors)
    message = _message(actors)
    await _invoke(actors, state, message, backend=BrokenRedis())
    assert await _counts(actors) == (0, 0, 0, 0)
    assert await state.get_state() == bot_support.SupportFlow.waiting_message.state
    assert "сек" in message.answer.await_args.args[0]
    assert not message.answer.await_args.args[0].startswith("✅")


@pytest.mark.asyncio
async def test_blank_text_does_not_consume_quota_or_clear_fsm(actors):
    state = await _waiting_state(actors)
    message = _message(actors, body="   ")
    await _invoke(actors, state, message)
    assert await _counts(actors) == (0, 0, 0, 0)
    assert await state.get_state() == bot_support.SupportFlow.waiting_message.state
    assert await actors.redis.get(f"abuse:support:user:{actors.customer.id}") is None
    assert not message.answer.await_args.args[0].startswith("✅")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["clear", "ack"])
async def test_postcommit_fsm_or_ack_failure_replays_without_new_quota_or_notice(
    actors, monkeypatch, failure,
):
    monkeypatch.setattr(settings, "support_message_rate_limit_per_minute", 1)
    state = await _waiting_state(actors)
    message = _message(actors)
    if failure == "clear":
        original_clear = state.clear
        failed = False

        async def fail_once():
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("Synthetic FSM clear failure")
            await original_clear()

        monkeypatch.setattr(state, "clear", fail_once)
    else:
        message.answer.side_effect = RuntimeError("Synthetic acknowledgement failure")

    with pytest.raises(RuntimeError):
        await _invoke(actors, state, message)
    assert await _counts(actors) == (1, 1, 1, 1)
    assert await actors.redis.get(f"abuse:support:user:{actors.customer.id}") == "1"

    message.answer.side_effect = None
    await _invoke(actors, state, message)
    assert await _counts(actors) == (1, 1, 1, 1)
    assert await actors.redis.get(f"abuse:support:user:{actors.customer.id}") == "1"
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_parallel_duplicate_telegram_messages_create_one_conversation(actors, monkeypatch):
    original_get = AsyncSession.get
    both_absent = asyncio.Event()
    absent_sessions = set()

    async def synchronize_absent_ticket(session, entity, ident, *args, **kwargs):
        row = await original_get(session, entity, ident, *args, **kwargs)
        if entity is SupportTicket and row is None and session not in absent_sessions:
            absent_sessions.add(session)
            if len(absent_sessions) == 2:
                both_absent.set()
            await asyncio.wait_for(both_absent.wait(), timeout=5)
        return row

    monkeypatch.setattr(AsyncSession, "get", synchronize_absent_ticket)
    first, second = await _waiting_state(actors), await _waiting_state(actors)
    message = _message(actors)
    await asyncio.wait_for(asyncio.gather(
        _invoke(actors, first, message), _invoke(actors, second, message),
    ), timeout=10)
    assert await _counts(actors) == (1, 1, 1, 1)
    assert await first.get_state() is None and await second.get_state() is None
    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args[0] == message.answer.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_same_message_replay_does_not_reopen_closed_ticket(actors, monkeypatch):
    monkeypatch.setattr(settings, "support_message_rate_limit_per_minute", 1)
    state = await _waiting_state(actors)
    message = _message(actors)
    await _invoke(actors, state, message)
    async with SessionFactory() as session:
        ticket = await session.scalar(select(SupportTicket).where(
            SupportTicket.user_id == actors.customer.id,
        ))
        ticket.status = "closed"
        await session.commit()
        ticket_id, updated_at = ticket.id, ticket.updated_at

    await _invoke(actors, state, message)
    assert await _counts(actors) == (1, 1, 1, 1)
    assert await actors.redis.get(f"abuse:support:user:{actors.customer.id}") == "1"
    async with SessionFactory() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        assert ticket.status == "closed"
        assert ticket.updated_at == updated_at
