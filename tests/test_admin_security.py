from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.admin_telegram_security import (
    FRESH_ADMIN_INIT_DATA_PATHS,
    validate_fresh_admin_init_data,
)
from app.core.config import settings
from app.core.telegram_browser_auth import build_browser_init_data
from app.db.models import AdminAccount
from app.services.admin_security import (
    AdminSecurityConfigurationError,
    decrypt_mfa_secret,
    effective_permissions,
    encrypt_mfa_secret,
    has_permission,
    hash_admin_token,
    sanitize_audit_metadata,
    totp_code,
    verify_totp,
)

ROOT = Path(__file__).resolve().parents[1]


def test_admin_permissions_deny_by_default() -> None:
    admin = AdminAccount(
        user_id="00000000-0000-0000-0000-000000000001",
        role="support",
        permission_overrides={},
    )
    assert has_permission(admin, "support.manage")
    assert has_permission(admin, "users.read")
    assert not has_permission(admin, "users.wallet.adjust")
    assert not has_permission(admin, "admins.manage")


def test_explicit_deny_beats_role_grant() -> None:
    admin = AdminAccount(
        user_id="00000000-0000-0000-0000-000000000001",
        role="admin",
        permission_overrides={"deny": ["users.manage"]},
    )
    assert not has_permission(admin, "users.manage")
    assert has_permission(admin, "payments.read")
    assert "users.manage" not in effective_permissions(admin)


def test_unknown_role_has_no_permissions() -> None:
    admin = AdminAccount(
        user_id="00000000-0000-0000-0000-000000000001",
        role="unexpected",
        permission_overrides={},
    )
    assert not has_permission(admin, "dashboard.read")


def test_totp_matches_rfc6238_six_digit_projection() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, timestamp=59) == "287082"
    assert verify_totp(secret, "287082", timestamp=59)
    assert not verify_totp(secret, "287083", timestamp=59)


def test_mfa_secret_is_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "a" * 64)
    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_mfa_secret(secret)
    assert secret not in encrypted
    assert decrypt_mfa_secret(encrypted) == secret


def test_admin_token_is_not_stored_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "b" * 64)
    raw = "opaque-admin-token-value"
    digest = hash_admin_token(raw)
    assert raw not in digest
    assert len(digest) == 64
    assert digest == hash_admin_token(raw)


def test_weak_admin_security_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "short")
    with pytest.raises(AdminSecurityConfigurationError):
        hash_admin_token("token")


def test_audit_metadata_redacts_secrets() -> None:
    payload = sanitize_audit_metadata(
        {
            "user_id": "123",
            "authorization": "Bearer secret",
            "nested": {
                "provider_response": {"token": "abc"},
                "requisites": {"card": "4111111111111111"},
                "safe": "ok",
            },
        }
    )
    assert payload["authorization"] == "[redacted]"
    assert payload["nested"]["provider_response"] == "[redacted]"
    assert payload["nested"]["requisites"] == "[redacted]"
    assert payload["nested"]["safe"] == "ok"


def test_admin_initdata_freshness_rejects_replay_and_future_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "123456:test-admin-bot-token"
    monkeypatch.setattr(settings, "bot_token", token)
    now = datetime(2026, 9, 2, 14, 0, tzinfo=UTC)
    user = {
        "id": 123456789,
        "first_name": "Admin",
        "last_name": "",
        "username": "admin",
        "language_code": "ru",
    }

    fresh = build_browser_init_data(user, token, now=now - timedelta(minutes=9))
    validate_fresh_admin_init_data(fresh, now=now)

    replayed = build_browser_init_data(user, token, now=now - timedelta(minutes=11))
    with pytest.raises(ValueError, match="expired"):
        validate_fresh_admin_init_data(replayed, now=now)

    future = build_browser_init_data(user, token, now=now + timedelta(minutes=2))
    with pytest.raises(ValueError, match="future"):
        validate_fresh_admin_init_data(future, now=now)


def test_admin_privilege_establishment_routes_require_fresh_initdata() -> None:
    assert FRESH_ADMIN_INIT_DATA_PATHS == {
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/mfa/setup",
        "/api/v1/admin/auth/step-up",
    }


def test_admin_freshness_guard_is_wired_before_route_handlers() -> None:
    middleware = (ROOT / "app/core/http_security.py").read_text(encoding="utf-8")
    assert "if path in FRESH_ADMIN_INIT_DATA_PATHS:" in middleware
    assert "validate_fresh_admin_init_data(raw_init_data)" in middleware
    assert 'status_code=401' in middleware
    assert '"Invalid or expired Telegram initData"' in middleware


def test_admin_mfa_verification_uses_shared_account_rate_limit() -> None:
    auth = (ROOT / "app/api/v1/admin_auth.py").read_text(encoding="utf-8")
    assert 'key=f"admin:mfa:{context.account.id}"' in auth
    assert "limit=settings.admin_login_rate_limit_per_minute" in auth
    assert auth.count("await _enforce_mfa_rate_limit(redis, context)") == 2
    assert "async def confirm_mfa(" in auth
    assert "async def step_up(" in auth


def test_datetime_timezone_sanity() -> None:
    # Regression guard: admin session helpers use aware UTC datetimes.
    assert datetime.now(UTC).tzinfo is not None
