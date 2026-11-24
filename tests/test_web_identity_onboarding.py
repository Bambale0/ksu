"""Authentication transport must not change the public onboarding contract."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.api import deps
from app.core.config import settings
from app.services.onboarding import OnboardingService


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["web", "telegram"])
@pytest.mark.parametrize(
    ("method", "path", "complete", "blocked"),
    [
        ("POST", "/api/v1/generations", False, True),
        ("POST", "/api/v1/generations", True, False),
        ("GET", "/api/v1/generations", False, False),
        ("POST", "/api/v1/generations/example/cancel", False, False),
    ],
)
async def test_current_user_onboarding_contract(
    monkeypatch, transport, method, path, complete, blocked
):
    monkeypatch.setattr(settings, "onboarding_enabled", True)
    monkeypatch.setattr(settings, "onboarding_version", "v3-experiment")
    monkeypatch.setattr(settings, "bot_token", "123456:test-token")
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    user = SimpleNamespace(id=uuid4(), is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock(), info={})
    request = Request({
        "type": "http", "method": method, "path": path, "scheme": "https",
        "server": ("roxy.example", 443), "headers": [(b"origin", b"https://roxy.example")],
    })
    monkeypatch.setattr(deps, "current_web_user_id", AsyncMock(return_value=user.id))
    monkeypatch.setattr(
        deps, "safe_parse_webapp_init_data",
        lambda *_: SimpleNamespace(user=SimpleNamespace(
            id=424242, first_name="Test", last_name=None, username=None, language_code="ru",
        )),
    )
    monkeypatch.setattr(deps.UserService, "get_or_create", AsyncMock(return_value=user))
    monkeypatch.setattr(deps, "ensure_bootstrap_admin", AsyncMock())
    monkeypatch.setattr(OnboardingService, "is_complete", AsyncMock(return_value=complete))
    init_data = "signed-test-data" if transport == "telegram" else None
    if blocked:
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user(request, session, init_data)
        assert exc.value.status_code == 428
        assert exc.value.detail == {"code": "onboarding_required", "version": "v3-experiment"}
        assert "current_user_id" not in session.info
    else:
        assert await deps.get_current_user(request, session, init_data) is user
        assert session.info["current_user_id"] == user.id


@pytest.mark.asyncio
async def test_explicit_onboarding_dependency_reports_effective_version(monkeypatch):
    monkeypatch.setattr(settings, "onboarding_version", "1")
    monkeypatch.setattr(OnboardingService, "is_complete", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as exc:
        await deps.get_onboarded_user(SimpleNamespace(id=uuid4()), SimpleNamespace())
    assert exc.value.status_code == 428
    assert exc.value.detail == {"code": "onboarding_required", "version": "2"}
