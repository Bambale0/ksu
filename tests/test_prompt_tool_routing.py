from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app.api.admin_deps import get_admin_context_base
from app.core.config import settings
from app.db.admin_models import AdminCommand, AdminRuntimeSetting
from app.db.models import AdminAccount, AdminSession, User
from app.db.session import SessionFactory
from app.main import app
from app.services.admin_policy import AdminPolicyError
from app.services.admin_runtime import AdminRuntimeService
from app.services.prompt_tool_routing import (
    configured_prompt_tool_routes,
    prompt_tool_route_options,
    validate_prompt_tool_routes,
)


QWEN = {"provider": "neironych", "model": "qwen3.8-max"}
GPT = {"provider": "nexus", "model": "gpt-6-sol"}
DEFAULT_ROUTES = {"image_analysis": [QWEN, GPT], "video_prompt": [QWEN, GPT]}


@pytest.fixture
def policy_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = f"test-prompt-tool-routes-{uuid.uuid4()}"
    monkeypatch.setattr("app.services.prompt_tool_routing.PROMPT_TOOL_ROUTES_SETTING_KEY", key)
    monkeypatch.setattr("app.services.admin_runtime.PROMPT_TOOL_ROUTES_SETTING_KEY", key)
    return key


async def seed_admin(session, *, role: str = "owner") -> AdminAccount:
    user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic prompt route admin")
    session.add(user)
    await session.flush()
    admin = AdminAccount(
        user_id=user.id, role=role, is_active=True, mfa_enabled=True, permission_overrides={},
    )
    session.add(admin)
    await session.flush()
    return admin


def test_only_verified_photo_and_video_routes_are_offered_and_copied() -> None:
    choices = [[QWEN, GPT], [GPT, QWEN], [QWEN], [GPT]]
    options = prompt_tool_route_options()
    assert options == {"image_analysis": choices, "video_prompt": choices}
    for route in choices:
        selected = {"image_analysis": route, "video_prompt": route}
        validated = validate_prompt_tool_routes(selected)
        assert validated == selected
        validated["image_analysis"][0]["model"] = "changed-by-caller"
        assert selected["image_analysis"][0]["model"] in {"qwen3.8-max", "gpt-6-sol"}
        assert validated["video_prompt"][0]["model"] in {"qwen3.8-max", "gpt-6-sol"}
    options["image_analysis"][0][0]["model"] = "changed-by-caller"
    assert prompt_tool_route_options()["image_analysis"][0] == [QWEN, GPT]


@pytest.mark.parametrize("routes", [
    None,
    [],
    {},
    {"image_analysis": [QWEN]},
    DEFAULT_ROUTES | {"prompt_builder": [QWEN]},
    DEFAULT_ROUTES | {"video_prompt": []},
    DEFAULT_ROUTES | {"video_prompt": "neironych"},
    DEFAULT_ROUTES | {"video_prompt": [QWEN, QWEN]},
    DEFAULT_ROUTES | {"video_prompt": [QWEN, GPT, QWEN]},
    DEFAULT_ROUTES | {"image_analysis": [{"provider": "kie", "model": "gpt-6-sol"}]},
    DEFAULT_ROUTES | {"image_analysis": [{"provider": "neironych", "model": "gpt-6-sol"}]},
    DEFAULT_ROUTES | {"image_analysis": [{"provider": "nexus", "model": "qwen3.8-max"}]},
    DEFAULT_ROUTES | {"image_analysis": [{"provider": "Neironych", "model": "qwen3.8-max"}]},
    DEFAULT_ROUTES | {"image_analysis": [{"provider": "neironych"}]},
    DEFAULT_ROUTES | {"image_analysis": [QWEN | {"url": "https://example.invalid"}]},
    DEFAULT_ROUTES | {"image_analysis": [None]},
])
def test_invalid_or_out_of_scope_routes_are_rejected(routes) -> None:
    with pytest.raises(ValueError):
        validate_prompt_tool_routes(routes)


async def test_default_policy_is_qwen_primary_without_a_database_write(policy_key: str) -> None:
    async with SessionFactory() as session:
        config = await configured_prompt_tool_routes(session)
        assert config == {"revision": 1, "routes": DEFAULT_ROUTES}
        assert await session.get(AdminRuntimeSetting, policy_key) is None
        config["routes"]["image_analysis"].reverse()
        assert await configured_prompt_tool_routes(session) == {"revision": 1, "routes": DEFAULT_ROUTES}


@pytest.mark.parametrize("role,confirmed,step_up_valid", [
    ("auditor", True, True),
    ("owner", False, True),
    ("owner", True, False),
])
async def test_service_requires_permission_confirmation_and_fresh_step_up(
    policy_key: str, role: str, confirmed: bool, step_up_valid: bool,
) -> None:
    async with SessionFactory() as session:
        admin = await seed_admin(session, role=role)
        with pytest.raises(AdminPolicyError):
            await AdminRuntimeService.set_prompt_tool_routes(
                session, admin=admin, routes=DEFAULT_ROUTES, expected_revision=1,
                idempotency_key=str(uuid.uuid4()), request_id=str(uuid.uuid4()),
                confirmed=confirmed, step_up_valid=step_up_valid,
            )
        assert await session.get(AdminRuntimeSetting, policy_key) is None


async def test_admin_api_authorizes_validates_replays_and_rejects_stale_writes(
    policy_key: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "synthetic-prompt-route-key-00000000000000000000")
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        admin = await seed_admin(session, role="auditor")
        admin_session = AdminSession(
            admin_id=admin.id, token_hash=uuid.uuid4().hex, created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1), idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True, step_up_until=now + timedelta(minutes=5), session_version=1,
        )
        session.add(admin_session)
        await session.commit()
        context = SimpleNamespace(
            account=admin, session=admin_session, user=await session.get(User, admin.user_id),
        )

        async def authenticated_context():
            return context

        app.dependency_overrides[get_admin_context_base] = authenticated_context
        try:
            path = "/api/v1/admin/runtime/prompt-tool-routes"
            selected = {"image_analysis": [GPT], "video_prompt": [QWEN, GPT]}
            payload = {"routes": selected, "expected_revision": 1}
            key = str(uuid.uuid4())
            headers = {"Idempotency-Key": key, "X-Admin-Confirm": "confirmed"}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
            ) as client:
                assert (await client.post(path, json=payload, headers=headers)).status_code == 403
                assert (await client.get("/api/v1/admin/runtime")).status_code == 403
                admin.role = "owner"
                admin_session.step_up_until = now - timedelta(seconds=1)
                await session.commit()
                denied = await client.post(path, json=payload, headers=headers)
                assert denied.status_code == 403 and "step-up" in denied.text
                admin_session.step_up_until = now + timedelta(minutes=5)
                await session.commit()
                assert (await client.post(path, json=payload, headers={"Idempotency-Key": key})).status_code == 403
                assert (await client.post(path, json=payload, headers={"X-Admin-Confirm": "confirmed"})).status_code == 400
                for invalid in (
                    payload | {"routes": selected | {"prompt_builder": [QWEN]}},
                    payload | {"routes": selected | {"video_prompt": [QWEN, QWEN]}},
                    payload | {"routes": selected | {"image_analysis": [QWEN | {"model": "gpt-6-sol"}]}},
                    payload | {"expected_revision": 0},
                    payload | {"expected_revision": True},
                    payload | {"user_routes": {}},
                ):
                    rejected = await client.post(
                        path, json=invalid, headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
                    )
                    assert rejected.status_code == 422, rejected.text

                initial = (await client.get("/api/v1/admin/runtime")).json()[policy_key]
                assert initial == {"revision": 1, "routes": DEFAULT_ROUTES, "options": prompt_tool_route_options()}
                saved = await client.post(path, json=payload, headers=headers)
                assert saved.status_code == 200, saved.text
                assert saved.json() == {"revision": 2, "routes": selected, "idempotency_replayed": False}
                replay = await client.post(path, json=payload, headers=headers)
                assert replay.status_code == 200, replay.text
                assert replay.json() == {"revision": 2, "routes": selected, "idempotency_replayed": True}
                conflict = await client.post(path, json=payload | {"routes": DEFAULT_ROUTES}, headers=headers)
                assert conflict.status_code == 409, conflict.text
                stale = await client.post(
                    path, json=payload, headers=headers | {"Idempotency-Key": str(uuid.uuid4())},
                )
                assert stale.status_code == 422 and "reload settings" in stale.text
                current = (await client.get("/api/v1/admin/runtime")).json()[policy_key]
                assert current == {"revision": 2, "routes": selected, "options": prompt_tool_route_options()}

            command = await session.scalar(select(AdminCommand).where(AdminCommand.idempotency_key == key))
            assert command is not None and command.status == "completed"
            assert command.action == "runtime.prompt_tool_routes"
            assert command.admin_user_id == admin.id and command.target_id == policy_key
            assert command.request_payload == payload
            assert command.response_payload == {"revision": 2, "routes": selected}
            row = await session.get(AdminRuntimeSetting, policy_key)
            assert row is not None and row.updated_by_admin_id == admin.id
        finally:
            app.dependency_overrides.pop(get_admin_context_base, None)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("same_command", [False, True])
async def test_concurrent_writes_share_one_revision_fence_and_replay_identity(
    policy_key: str, existing: bool, same_command: bool,
) -> None:
    revision = 8 if existing else 1
    async with SessionFactory() as session:
        admin = await seed_admin(session)
        if existing:
            session.add(AdminRuntimeSetting(
                key=policy_key, value={"revision": revision, "routes": DEFAULT_ROUTES},
                updated_by_admin_id=admin.id,
            ))
        await session.commit()
        admin_id = admin.id

    barrier = asyncio.Barrier(2)
    command_key = str(uuid.uuid4())

    async def save(index: int):
        routes = deepcopy(DEFAULT_ROUTES)
        routes["image_analysis"] = [GPT] if same_command or index == 0 else [QWEN]
        async with SessionFactory() as session:
            actor = await session.get(AdminAccount, admin_id)
            await barrier.wait()
            try:
                result = await AdminRuntimeService.set_prompt_tool_routes(
                    session, admin=actor, routes=routes, expected_revision=revision,
                    idempotency_key=command_key if same_command else f"{command_key}-{index}",
                    request_id=str(uuid.uuid4()), confirmed=True, step_up_valid=True,
                )
                await session.commit()
                return result
            except ValueError as exc:
                await session.rollback()
                assert "changed" in str(exc)
                return None

    results = await asyncio.gather(save(0), save(1))
    successful = [result for result in results if result is not None]
    assert len(successful) == (2 if same_command else 1)
    assert sorted(replayed for _value, replayed in successful) == ([False, True] if same_command else [False])
    final = successful[0][0]
    assert final["revision"] == revision + 1
    async with SessionFactory() as session:
        assert await configured_prompt_tool_routes(session) == final
        assert await session.scalar(select(func.count()).select_from(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == policy_key,
        )) == 1
        assert await session.scalar(select(func.count()).select_from(AdminCommand).where(
            AdminCommand.target_id == policy_key, AdminCommand.status == "completed",
        )) == 1
