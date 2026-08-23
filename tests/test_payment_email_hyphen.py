from pathlib import Path

import pytest

from app.services.billing_email import normalize_billing_email

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
GUARD = ROOT / "frontend" / "mini-app" / "components" / "wallet-email-input-guard.tsx"
API = ROOT / "app" / "api" / "v1" / "card_payments.py"


def test_billing_email_accepts_ascii_hyphenated_addresses() -> None:
    assert (
        normalize_billing_email(" User-Name@Sub-Domain.Example ")
        == "user-name@sub-domain.example"
    )


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
        normalize_billing_email(value)


def test_card_checkout_normalizes_billing_email_before_service_call() -> None:
    source = API.read_text(encoding="utf-8")
    assert "from app.services.billing_email import normalize_billing_email" in source
    assert "billing_email=normalize_billing_email(payload.billing_email)" in source


def test_wallet_email_guard_is_mounted_for_telegram_webview() -> None:
    page = PAGE.read_text(encoding="utf-8")
    guard = GUARD.read_text(encoding="utf-8")
    assert 'import { WalletEmailInputGuard } from "@/components/wallet-email-input-guard";' in page
    assert "<WalletEmailInputGuard />" in page
    assert 'input.type === "email"' in guard
    assert 'input.type = "text"' in guard
    assert "input.inputMode = \"email\"" in guard
    assert "replace(DASHES, \"-\")" in guard
