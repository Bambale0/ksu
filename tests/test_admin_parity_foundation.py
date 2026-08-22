import uuid

import pytest

from app.db.models import AdminAccount
from app.services.admin_commands import payload_hash, redact_secrets
from app.services.admin_notifications import CampaignValidationError, validate_campaign_segment
from app.services.admin_policy import AdminPolicy, AdminPolicyError
from app.services.admin_pricing import TariffValidationError, validate_tariff_payload
from app.services.internal_admin_security import (
    calculate_signature,
    ip_allowed,
    verify_timestamp,
)


def _admin(role: str = "admin") -> AdminAccount:
    return AdminAccount(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
        permission_overrides={},
        is_active=True,
    )


def test_internal_admin_hmac_is_exact_body_sensitive() -> None:
    secret = "s" * 48
    common = {
        "timestamp": 1_700_000_000,
        "request_id": "req-123",
        "method": "POST",
        "path": "/internal/admin/users/abc/balance-adjustments",
    }
    first = calculate_signature(secret, raw_body=b'{"amount":"10"}', **common)
    second = calculate_signature(secret, raw_body=b'{ "amount":"10"}', **common)
    assert first != second
    assert len(first) == 64


def test_internal_admin_allowlist_is_cidr_based_and_fail_closed() -> None:
    allowlist = "127.0.0.1/32,10.20.0.0/16,2001:db8::/32"
    assert ip_allowed("127.0.0.1", allowlist)
    assert ip_allowed("10.20.4.8", allowlist)
    assert ip_allowed("2001:db8::5", allowlist)
    assert not ip_allowed("10.21.4.8", allowlist)
    assert not ip_allowed(None, allowlist)
    assert not ip_allowed("not-an-ip", allowlist)


def test_internal_admin_timestamp_skew() -> None:
    assert verify_timestamp(100, now=105, skew_seconds=5)
    assert not verify_timestamp(100, now=106, skew_seconds=5)


def test_admin_command_redaction_is_recursive() -> None:
    payload = {
        "safe": "ok",
        "token": "secret-token",
        "nested": {
            "api_key": "secret-key",
            "callback": {"authorization": "Bearer secret"},
            "items": [{"webhook": "https://secret.invalid"}, {"value": 3}],
        },
    }
    redacted = redact_secrets(payload)
    assert redacted["safe"] == "ok"
    assert redacted["token"] == "[redacted]"
    assert redacted["nested"]["api_key"] == "[redacted]"
    assert redacted["nested"]["callback"] == "[redacted]"
    assert redacted["nested"]["items"][0]["webhook"] == "[redacted]"


def test_payload_hash_is_order_independent_but_content_sensitive() -> None:
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


def test_admin_policy_supplements_existing_roles_and_preserves_deny() -> None:
    admin = _admin("admin")
    assert AdminPolicy.has_permission(admin, "pricing.manage")
    assert AdminPolicy.has_permission(admin, "notifications.manage")
    admin.permission_overrides = {"deny": ["pricing.manage"]}
    assert not AdminPolicy.has_permission(admin, "pricing.manage")


def test_admin_policy_confirmation_and_step_up_are_explicit() -> None:
    admin = _admin("admin")
    with pytest.raises(AdminPolicyError, match="confirmation"):
        AdminPolicy.authorize_action(
            admin,
            "users.balance_adjust",
            confirmed=False,
            step_up_valid=True,
        )
    with pytest.raises(AdminPolicyError, match="MFA"):
        AdminPolicy.authorize_action(
            admin,
            "users.balance_adjust",
            confirmed=True,
            step_up_valid=False,
        )
    AdminPolicy.authorize_action(
        admin,
        "users.balance_adjust",
        confirmed=True,
        step_up_valid=True,
    )


def test_tariff_validation_rejects_unknown_and_negative_values() -> None:
    valid = validate_tariff_payload(
        {
            "packages": {"starter": {"credits": 50, "rub": 500}},
            "video_prices": {"kling": {"per_second": 2.5}},
        }
    )
    assert valid["video_prices"]["kling"]["per_second"] == 2.5
    with pytest.raises(TariffValidationError, match="Unknown"):
        validate_tariff_payload({"hidden_provider_secret": {"x": 1}})
    with pytest.raises(TariffValidationError, match="Negative"):
        validate_tariff_payload({"image_prices": {"model": -1}})


def test_admin_generation_pricing_tiers_follow_model_ui_contract() -> None:
    valid = validate_tariff_payload(
        {
            "generation_pricing": {
                "kling-motion-3.0": {
                    "per_second": 60,
                    "by_mode": {"720p": 60, "1080p": 80},
                },
                "veo-3.1": {
                    "per_second": 35,
                    "by_resolution": {"720p": 35, "1080p": 50, "4k": 80},
                },
            }
        }
    )
    assert valid["generation_pricing"]["kling-motion-3.0"]["by_mode"]["1080p"] == 80

    with pytest.raises(TariffValidationError, match="unsupported resolution"):
        validate_tariff_payload(
            {
                "generation_pricing": {
                    "veo-3.1": {
                        "per_second": 35,
                        "by_resolution": {"1440p": 50},
                    }
                }
            }
        )

    with pytest.raises(TariffValidationError, match="unsupported mode"):
        validate_tariff_payload(
            {
                "generation_pricing": {
                    "kling-motion-3.0": {
                        "per_second": 60,
                        "by_mode": {"4K": 100},
                    }
                }
            }
        )


def test_campaign_segment_validation_is_bounded() -> None:
    user_id = uuid.uuid4()
    segment = validate_campaign_segment(
        {"active_only": True, "user_ids": [str(user_id)], "language_codes": ["ru"]}
    )
    assert segment["user_ids"] == [str(user_id)]
    with pytest.raises(CampaignValidationError, match="Unknown"):
        validate_campaign_segment({"sql": "drop table users"})
    with pytest.raises(CampaignValidationError, match="UUID"):
        validate_campaign_segment({"user_ids": ["not-a-uuid"]})
