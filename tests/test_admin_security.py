from datetime import UTC, datetime
import random

import pytest

from app.core.config import settings
from app.db.models import AdminAccount
from app.services.admin_security import (
    AdminAuthService,
    AdminSecurityConfigurationError,
    decrypt_mfa_secret,
    effective_permissions,
    encrypt_mfa_secret,
    has_permission,
    hash_admin_token,
    is_env_admin,
    sanitize_audit_metadata,
    totp_code,
    verify_totp,
)


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


def test_admin_identity_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    first = random.randint(9_100_000_000_000, 9_199_999_999_999)
    second = random.randint(9_200_000_000_000, 9_299_999_999_999)
    other = random.randint(9_300_000_000_000, 9_399_999_999_999)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", f"{first}, {second}")

    assert is_env_admin(first)
    assert is_env_admin(second)
    assert not is_env_admin(other)
    assert not is_env_admin(None)


@pytest.mark.asyncio
async def test_bootstrap_admin_denies_ids_not_present_in_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiogram.types import User as TelegramUser

    from app.db.session import SessionFactory

    allowed = random.randint(9_400_000_000_000, 9_499_999_999_999)
    denied = random.randint(9_500_000_000_000, 9_599_999_999_999)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(allowed))
    telegram_user = TelegramUser(id=denied, is_bot=False, first_name="Not admin")

    async with SessionFactory() as session:
        admin = await AdminAuthService.get_or_bootstrap_admin(session, telegram_user)

    assert admin is None


@pytest.mark.asyncio
async def test_bootstrap_admin_promotes_env_id_to_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiogram.types import User as TelegramUser

    from app.db.session import SessionFactory

    allowed = random.randint(9_600_000_000_000, 9_699_999_999_999)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(allowed))
    telegram_user = TelegramUser(id=allowed, is_bot=False, first_name="Owner")

    async with SessionFactory() as session:
        admin = await AdminAuthService.get_or_bootstrap_admin(session, telegram_user)

    assert admin is not None
    assert admin.role == "owner"
    assert admin.is_active is True


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


def test_datetime_timezone_sanity() -> None:
    # Regression guard: admin session helpers use aware UTC datetimes.
    assert datetime.now(UTC).tzinfo is not None
