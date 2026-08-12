from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_payment_link_guard_is_loaded_before_wallet_checkout() -> None:
    html = _read("index.html")
    guard_pos = html.index('/mini-app/payment-link-guard.js')
    wallet_pos = html.index('/mini-app/wallet.js')
    assert guard_pos < wallet_pos


def test_payment_link_guard_requires_https_and_direct_activation() -> None:
    guard = _read("payment-link-guard.js")
    assert 'parsed.protocol === "https:"' in guard
    assert "directUserActivation" in guard
    assert 'window.addEventListener("click", markActivation, true)' in guard
    assert "queueMicrotask" in guard
    assert "withDirectActivation(tg.openLink)" in guard
    assert "withDirectActivation(tg.openTelegramLink)" in guard


def test_wallet_keeps_separate_direct_open_button_for_created_payment() -> None:
    wallet = _read("wallet.js")
    assert 'reopen.textContent = "Открыть оплату"' in wallet
    assert 'reopen.addEventListener("click"' in wallet
    assert "openPaymentUrl(payment.payment_url)" in wallet
