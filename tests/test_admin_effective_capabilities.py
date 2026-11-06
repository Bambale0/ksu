from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.router import api_router
from app.core.config import settings
from app.core.telegram_browser_auth import build_browser_init_data
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.services.admin_policy import AdminPolicy, ROLE_PERMISSION_SUPPLEMENTS
from app.services.admin_security import (
    ROLE_PERMISSIONS,
    effective_permissions,
    encrypt_mfa_secret,
    has_permission,
    totp_code,
)

BOT_TOKEN = "123456:isolated-capability-test-bot-token"
MFA_SECRET = "JBSWY3DPEHPK3PXP"
OWNER_ONLY_PERMISSIONS = {"admins.manage"}
REGISTERED_PERMISSIONS = (
    set().union(*ROLE_PERMISSIONS.values(), *ROLE_PERMISSION_SUPPLEMENTS.values())
    | OWNER_ONLY_PERMISSIONS
) - {"*"}


@pytest.fixture(autouse=True)
def configured_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "admin_security_key", "isolated-capability-contract-key-20261106")
    monkeypatch.setattr(settings, "admin_require_mfa", True)
    monkeypatch.setattr(settings, "admin_login_rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings, "admin_request_rate_limit_per_minute", 1000)


async def actor(
    role: str,
    overrides: dict[str, list[str]],
    *,
    mfa_enabled: bool = True,
) -> tuple[AdminAccount, str]:
    telegram_id = 9_300_000_000_000 + uuid.uuid4().int % 100_000_000_000
    async with SessionFactory() as session:
        user = User(telegram_id=telegram_id, first_name="Capability regression", is_active=True)
        session.add(user)
        await session.flush()
        account = AdminAccount(
            user_id=user.id,
            role=role,
            permission_overrides=overrides,
            is_active=True,
            mfa_enabled=mfa_enabled,
            mfa_secret_encrypted=encrypt_mfa_secret(MFA_SECRET) if mfa_enabled else None,
        )
        session.add(account)
        await session.commit()
    init_data = build_browser_init_data(
        {"id": telegram_id, "first_name": "Capability regression"}, BOT_TOKEN,
    )
    return account, init_data


@asynccontextmanager
async def auth_client():
    app = FastAPI()
    app.include_router(api_router)
    redis = Redis.from_url(settings.redis_url)
    app.state.redis = redis
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client
    finally:
        await redis.aclose()


def permits(permissions: list[str], permission: str) -> bool:
    return "*" in permissions or permission in permissions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "overrides", "required", "forbidden"),
    [
        ("admin", {}, {"runtime.manage", "pricing.read", "cms.read", "partners.read"}, {"admins.manage"}),
        ("finance", {}, {"finance.read", "pricing.read", "partners.read", "payments.manage"}, {"runtime.manage", "support.read"}),
        ("support", {}, {"operations.read", "support.manage"}, {"pricing.read"}),
        ("moderator", {}, {"prompts.manage", "social.moderate", "cms.read"}, {"pricing.manage"}),
        ("auditor", {}, {"notifications.read", "finance.read", "pricing.read"}, {"pricing.manage"}),
        ("admin", {"deny": ["pricing.read", "users.read"]}, {"operations.read"}, {"pricing.read", "users.read"}),
        ("finance", {"allow": ["custom.read"], "deny": ["partners.read"]}, {"pricing.read", "custom.read"}, {"partners.read"}),
        ("admin", {"allow": ["custom.read", "*"], "deny": ["*"]}, set(), {"custom.read", "users.read", "pricing.read"}),
        ("owner", {}, {"admins.manage", "runtime.manage", "custom.unregistered"}, set()),
        ("owner", {"deny": ["pricing.read"]}, {"admins.manage", "runtime.manage"}, {"pricing.read"}),
        ("owner", {"allow": ["custom.read"], "deny": ["users.read"]}, {"custom.read", "admins.manage"}, {"users.read"}),
        ("owner", {"deny": ["*"]}, set(), {"admins.manage", "runtime.manage"}),
        ("support", {"allow": ["*"]}, {"admins.manage", "runtime.manage", "custom.unregistered"}, set()),
        ("support", {"allow": ["*", "custom.read"], "deny": ["payments.read"]}, {"admins.manage", "runtime.manage", "custom.read"}, {"payments.read"}),
        ("support", {"allow": ["custom.read"], "deny": ["custom.read"]}, {"operations.read"}, {"custom.read"}),
    ],
    ids=[
        "admin-supplements", "finance-supplements", "support-supplement",
        "moderator-supplements", "auditor-supplements", "base-and-supplement-deny",
        "explicit-allow", "deny-all-beats-allow", "owner-wildcard",
        "owner-exact-deny", "owner-deny-keeps-custom-allow", "owner-deny-all",
        "explicit-wildcard", "explicit-wildcard-with-deny", "deny-beats-exact-allow",
    ],
)
async def test_signed_login_and_me_publish_effective_policy(
    role, overrides, required, forbidden,
):
    account, init_data = await actor(role, overrides)
    async with auth_client() as client:
        login = await client.post(
            "/api/v1/admin/auth/login",
            headers={"X-Telegram-Init-Data": init_data},
            json={"otp": totp_code(MFA_SECRET)},
        )
        assert login.status_code == 200, login.text
        payload = login.json()
        assert payload["mfa_verified"] is True
        me = await client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {payload['token']}"},
        )
        assert me.status_code == 200, me.text

    # Both public auth responses must describe the endpoint gate, not a legacy role subset.
    assert payload["permissions"] == me.json()["permissions"]
    advertised = payload["permissions"]
    for permission in required:
        assert AdminPolicy.has_permission(account, permission)
        assert permits(advertised, permission), (role, permission, advertised)
    for permission in forbidden:
        assert not AdminPolicy.has_permission(account, permission)
        assert not permits(advertised, permission), (role, permission, advertised)
    candidates = REGISTERED_PERMISSIONS | (set(overrides.get("allow", [])) - {"*"})
    for permission in candidates:
        assert permits(advertised, permission) == AdminPolicy.has_permission(account, permission), (
            role, permission, advertised,
        )


@pytest.mark.asyncio
async def test_unverified_mfa_session_advertises_no_permissions():
    _, init_data = await actor("admin", {}, mfa_enabled=False)
    async with auth_client() as client:
        login = await client.post(
            "/api/v1/admin/auth/login",
            headers={"X-Telegram-Init-Data": init_data},
            json={},
        )
        assert login.status_code == 200, login.text
        payload = login.json()
        assert payload["mfa_setup_required"] is True
        assert payload["permissions"] == []
        me = await client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {payload['token']}"},
        )
        assert me.status_code == 200, me.text
        assert me.json()["permissions"] == []


@pytest.mark.asyncio
async def test_deactivated_admin_cannot_reuse_real_session_or_login():
    account, init_data = await actor("owner", {})
    async with auth_client() as client:
        login = await client.post(
            "/api/v1/admin/auth/login",
            headers={"X-Telegram-Init-Data": init_data},
            json={"otp": totp_code(MFA_SECRET)},
        )
        assert login.status_code == 200, login.text
        async with SessionFactory() as session:
            stored = await session.get(AdminAccount, account.id)
            stored.is_active = False
            await session.commit()
        me = await client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {login.json()['token']}"},
        )
        assert me.status_code == 401, me.text
        retry = await client.post(
            "/api/v1/admin/auth/login",
            headers={"X-Telegram-Init-Data": init_data},
            json={"otp": totp_code(MFA_SECRET)},
        )
        assert retry.status_code == 403, retry.text
    account.is_active = False
    assert not AdminPolicy.has_permission(account, "admins.manage")
    assert effective_permissions(account) == []


def test_legacy_permission_helper_keeps_its_existing_grants():
    account = AdminAccount(
        user_id=uuid.uuid4(), role="finance", permission_overrides={}, is_active=True,
    )
    assert has_permission(account, "payments.read")
    assert not has_permission(account, "pricing.read")
    assert AdminPolicy.has_permission(account, "pricing.read")


def test_policy_predicate_preserves_all_previous_role_and_override_grants():
    override_cases = [
        {},
        {"allow": ["custom.read"]},
        {"deny": ["users.read", "pricing.read"]},
        {"allow": ["pricing.read"], "deny": ["pricing.read"]},
        {"allow": ["*"]},
        {"allow": ["*", "custom.read"], "deny": ["payments.read"]},
        {"deny": ["*"]},
        {"allow": ["*", "custom.read"], "deny": ["*"]},
        {"deny": ["future.unknown"]},
    ]
    permissions = REGISTERED_PERMISSIONS | {"custom.read", "future.unknown", "*"}
    for role in (*ROLE_PERMISSIONS, "unregistered"):
        for active in (True, False):
            for overrides in override_cases:
                account = AdminAccount(
                    user_id=uuid.uuid4(), role=role, permission_overrides=overrides,
                    is_active=active,
                )
                base = ROLE_PERMISSIONS.get(role, frozenset())
                supplement = ROLE_PERMISSION_SUPPLEMENTS.get(role, frozenset())
                allow = set(overrides.get("allow", []))
                deny = set(overrides.get("deny", []))
                for permission in permissions:
                    denied = "*" in deny or permission in deny
                    legacy_granted = not denied and (
                        "*" in base or permission in base
                        or "*" in allow or permission in allow
                    )
                    policy_granted = active and not denied and (
                        legacy_granted or permission in supplement
                    )
                    context = (role, active, overrides, permission)
                    assert has_permission(account, permission) == legacy_granted, context
                    assert AdminPolicy.has_permission(account, permission) == policy_granted, context


def test_wildcard_with_deny_preserves_every_registered_route_and_action_permission():
    # Catch additions to endpoint/action gates that a finite UI expansion might omit.
    import ast
    import re
    from pathlib import Path

    from app.services.admin_policy import ACTION_POLICIES

    registered = REGISTERED_PERMISSIONS | {policy.permission for policy in ACTION_POLICIES.values()}
    for path in (Path(__file__).resolve().parents[1] / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            if name not in {"require_permission", "has_permission", "AdminActionPolicy"}:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)+", arg.value):
                        registered.add(arg.value)
    account = AdminAccount(
        user_id=uuid.uuid4(), role="owner",
        permission_overrides={"deny": ["users.read"]}, is_active=True,
    )
    advertised = effective_permissions(account)
    assert "*" not in advertised
    assert set(advertised) == registered - {"users.read"}
    # The finite UI list must never narrow the server's open-ended wildcard policy.
    assert AdminPolicy.has_permission(account, "future.unknown")
