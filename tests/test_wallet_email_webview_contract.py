from pathlib import Path

from app.services.payment_email import normalize_billing_email, validate_billing_email


ROOT = Path(__file__).resolve().parents[1]


def test_billing_email_accepts_hyphens_and_mobile_dash_lookalikes() -> None:
    assert validate_billing_email("User-Name@Sub-Domain.Example") == "user-name@sub-domain.example"
    assert normalize_billing_email("User\u2011Name@Sub\u2013Domain.Example") == "user-name@sub-domain.example"
    assert validate_billing_email("User\u2011Name@Sub\u2013Domain.Example") == "user-name@sub-domain.example"


def test_wallet_email_guard_avoids_native_webview_email_validation() -> None:
    source = (ROOT / "frontend/mini-app/components/wallet-email-input-guard.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend/mini-app/app/page.tsx").read_text(encoding="utf-8")

    assert 'input.type = "text"' in source
    assert 'input.inputMode = "email"' in source
    assert "DASHES" in source
    assert 'dispatchEvent(new Event("input", { bubbles: true }))' in source
    assert '<WalletEmailInputGuard />' in page
