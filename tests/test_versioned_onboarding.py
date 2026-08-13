from pathlib import Path

import pytest
from fastapi import Request
from sqlalchemy import func, select

from app.api.deps import _onboarding_gate_applies
from app.api.v1.onboarding import complete_onboarding, onboarding_status
from app.bot.keyboards import onboarding_menu
from app.core.config import settings
from app.db.models import User
from app.db.onboarding_models import UserOnboarding
from app.db.session import SessionFactory
from app.services.onboarding import OnboardingService

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


@pytest.mark.asyncio
async def test_onboarding_completion_is_idempotent_and_versioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "onboarding_enabled", True)
    monkeypatch.setattr(settings, "onboarding_version", "v1")
    async with SessionFactory() as session:
        user = User(telegram_id=960000000000001, first_name="Onboarding")
        session.add(user)
        await session.commit()

        initial = await onboarding_status(user, session)
        assert initial["enabled"] is True
        assert initial["version"] == "v1"
        assert initial["completed"] is False

        completed = await complete_onboarding(user, session)
        assert completed["completed"] is True
        assert completed["completed_version"] == "v1"

        repeated = await complete_onboarding(user, session)
        assert repeated["completed"] is True
        count = await session.scalar(select(func.count()).select_from(UserOnboarding))
        assert int(count or 0) == 1

        monkeypatch.setattr(settings, "onboarding_version", "v2")
        bumped = await onboarding_status(user, session)
        assert bumped["completed"] is False
        assert bumped["completed_version"] == "v1"

        completed_v2 = await complete_onboarding(user, session)
        assert completed_v2["completed"] is True
        assert completed_v2["completed_version"] == "v2"
        count = await session.scalar(select(func.count()).select_from(UserOnboarding))
        assert int(count or 0) == 1


@pytest.mark.asyncio
async def test_onboarding_disabled_is_complete_and_external_links_require_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=960000000000002, first_name="Disabled")
        session.add(user)
        await session.commit()

        monkeypatch.setattr(settings, "onboarding_enabled", False)
        monkeypatch.setattr(settings, "onboarding_rules_url", "http://insecure.example/rules")
        monkeypatch.setattr(settings, "onboarding_privacy_url", "https://example.com/privacy")
        status = await OnboardingService.status(session, user.id)
        assert status["completed"] is True
        assert status["rules_url"] is None
        assert status["privacy_url"] == "https://example.com/privacy"


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/v1/generations", False),
        ("DELETE", "/api/v1/social/profiles/a/subscribe", False),
        ("POST", "/api/v1/onboarding/complete", False),
        ("POST", "/api/v1/support/tickets", False),
        ("POST", "/api/v1/notifications/read-all", False),
        ("PUT", "/api/v1/me/preferences", False),
        ("POST", "/api/v1/referrals/withdrawals/a/cancel", False),
        ("POST", "/api/v1/generations", True),
        ("POST", "/api/v1/payments", True),
        ("POST", "/api/v1/promocodes/redeem", True),
        ("POST", "/api/v1/uploads", True),
        ("POST", "/api/v1/social/profiles/a/subscribe", True),
        ("POST", "/api/v1/referrals/withdrawals", True),
    ],
)
def test_business_mutation_gate_policy(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(settings, "onboarding_enabled", True)
    assert _onboarding_gate_applies(_request(method, path)) is expected


def test_onboarding_bot_keyboard_uses_only_configured_https_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "onboarding_rules_url", "https://example.com/rules")
    monkeypatch.setattr(settings, "onboarding_privacy_url", "https://example.com/privacy")
    keyboard = onboarding_menu()
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == ["Правила", "Конфиденциальность", "🚀 Начать"]
    assert keyboard.inline_keyboard[-1][0].callback_data == "onboarding_complete"


def test_onboarding_client_is_server_versioned_and_blocks_shell() -> None:
    script = (MINI / "onboarding.js").read_text(encoding="utf-8")
    for token in (
        'api("/api/v1/onboarding")',
        'api("/api/v1/onboarding/complete", { method: "POST" })',
        "appShell.inert",
        'appShell.setAttribute("aria-hidden"',
        "response.status === 428",
        'payload?.detail?.code === "onboarding_required"',
        'url.protocol === "https:"',
        "tg.openLink(safe)",
        'new CustomEvent("ksu:onboarding-complete"',
    ):
        assert token in script, token
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "initDataUnsafe" not in script
    assert "accept_terms" not in script
    assert "legal_accepted" not in script


def test_onboarding_module_is_mounted_and_checked_by_ci() -> None:
    integration = (MINI / "shell-integration.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'stylesheet.href = "/mini-app/onboarding.css"' in integration
    assert 'script.src = "/mini-app/onboarding.js"' in integration
    assert "mountOnboarding();" in integration
    assert integration.index("mountOnboarding();") < integration.index("mountPartnerCabinet();")
    assert "node --check app/web/mini_app/onboarding.js" in workflow
    assert 'ONBOARDING_ENABLED: "false"' in workflow
    assert "ONBOARDING_ENABLED=true" in env_example
    assert "ONBOARDING_VERSION=1" in env_example
    assert (MINI / "onboarding.css").is_file()


def test_legacy_bot_generation_flow_rechecks_onboarding() -> None:
    start_source = (ROOT / "app" / "bot" / "handlers" / "start.py").read_text(encoding="utf-8")
    generation_source = (ROOT / "app" / "bot" / "handlers" / "generation.py").read_text(
        encoding="utf-8"
    )
    assert 'F.data == "onboarding_complete"' in start_source
    assert "await OnboardingService.complete(session, user.id)" in start_source
    assert generation_source.count("await OnboardingService.is_complete(session, user.id)") >= 2
    assert "await state.clear()" in generation_source
    assert "onboarding_menu()" in generation_source
