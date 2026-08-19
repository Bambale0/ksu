from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_payment_surface_mounts_before_telegram_guard_and_after_lava_checkout() -> None:
    guard = _read("payment-link-guard.js")
    assert '/mini-app/payment-surface.css' in guard
    assert '/mini-app/primary-card-checkout.js' in guard
    assert '/mini-app/payment-surface.js' in guard
    assert 'loadExtension("/mini-app/primary-card-checkout.js", () =>' in guard
    assert guard.index('loadStyle("/mini-app/payment-surface.css")') < guard.index(
        "const tg = window.Telegram?.WebApp"
    )


def test_payment_surface_exposes_only_lavatop_and_cryptobot() -> None:
    script = _read("payment-surface.js")
    css = _read("payment-surface.css")
    assert 'methodButton("lava", "Lava.top"' in script
    assert 'methodButton("crypto", "CryptoBot"' in script
    assert 'VISIBLE_PROVIDER = "cryptobot"' in script
    assert '[data-payment-provider="tbank"]' in script
    assert '[data-payment-provider="yookassa"]' in script
    assert '[data-payment-provider="tbank"]' in css
    assert '[data-payment-provider="yookassa"]' in css
    assert "node.remove()" in script
    assert 'dataset.checkoutProvider = "lavatop"' in script


def test_payment_surface_keeps_signed_telegram_context_and_syncs_chrome() -> None:
    script = _read("payment-surface.js")
    guard = _read("payment-link-guard.js")
    assert "Telegram?.WebApp" in script
    assert "themeChanged" in script
    assert "setHeaderColor" in script
    assert "setBackgroundColor" in script
    assert "setBottomBarColor" in script
    assert 'meta[name="theme-color"]' in script
    assert "isAllowedPaymentUrl" in guard
    assert 'parsed.protocol === "https:"' in guard


def test_payment_theme_has_explicit_light_and_dark_brand_palettes() -> None:
    css = _read("payment-surface.css")
    assert 'html[data-ksu-theme="dark"]' in css
    assert 'html[data-ksu-theme="light"]' in css
    assert "--button: #7768f5" in css
    assert "--button: #6757e5" in css
    assert "--ksu-lava: #ff765a" in css
    assert "--ksu-crypto: #35a9f2" in css
    assert ".payment-method-icon.lava" in css
    assert ".payment-method-icon.crypto" in css
    assert ".studio-sidebar" in css
    assert ".hero-card" in css
    assert "prefers-reduced-motion" in css
