from pathlib import Path

import pytest

from app.services.payment_email import normalize_billing_email, validate_billing_email

ROOT = Path(__file__).resolve().parents[1]
PAYMENTS_PAGE = ROOT / "frontend" / "mini-app" / "app" / "payments" / "page.tsx"
CARD_API = ROOT / "app" / "api" / "v1" / "card_payments.py"


def test_billing_email_accepts_ascii_hyphenated_addresses() -> None:
    assert validate_billing_email(" User-Name@Sub-Domain.Example ") == "user-name@sub-domain.example"


def test_billing_email_normalizes_mobile_dash_variants() -> None:
    assert normalize_billing_email("user\u2011name@example-domain.com") == "user-name@example-domain.com"
    assert normalize_billing_email("user-name@example\u2013domain.com") == "user-name@example-domain.com"


@pytest.mark.parametrize(
    "value",
    [
        "user name@example.com",
        "user@example",
        "user@-example.com",
        "user@example-.com",
        "@example.com",
    ],
)
def test_billing_email_rejects_invalid_addresses(value: str) -> None:
    with pytest.raises(ValueError, match="email"):
        validate_billing_email(value)


def test_card_checkout_validates_normalized_billing_email_before_service_call() -> None:
    source = CARD_API.read_text(encoding="utf-8")
    validation = "billing_email = validate_billing_email(payload.billing_email)"
    service_argument = "billing_email=billing_email"
    assert validation in source
    assert service_argument in source
    assert source.index(validation) < source.index(service_argument)


def test_payments_page_uses_webview_safe_email_keyboard_without_native_email_validation() -> None:
    source = PAYMENTS_PAGE.read_text(encoding="utf-8")
    assert 'type="text" inputMode="email" autoComplete="email"' in source
    assert 'type="email"' not in source
