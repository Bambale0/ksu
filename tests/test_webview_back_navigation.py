from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TELEGRAM = ROOT / "frontend" / "mini-app" / "lib" / "telegram.ts"
STANDALONE = ROOT / "frontend" / "mini-app" / "components" / "standalone-shell.tsx"


def test_customer_webview_back_uses_owned_history_and_closes_at_root() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    assert "roxyRootEntry" in source
    assert "stampMiniAppRootEntry" in source
    assert 'url.searchParams.set("route", "home")' in source
    assert "window.history.back()" in source
    assert "tg.close?.()" in source
    assert 'document.querySelector(".roxy-app .bottom-nav")' in source


def test_root_back_button_stays_visible_for_customer_shell() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    assert "if (isMainMiniAppPath()) rawShow?.();" in source
    assert "else rawHide?.();" in source
    assert "if (!handleCustomerBack(tg)) callback();" in source


def test_standalone_back_returns_to_exact_previous_mini_app_location() -> None:
    telegram = TELEGRAM.read_text(encoding="utf-8")
    standalone = STANDALONE.read_text(encoding="utf-8")
    assert "consumeMiniAppReturnLocation" in telegram
    assert "MINI_APP_RETURN_KEY" in telegram
    assert "pagehide" in telegram
    assert "consumeMiniAppReturnLocation" in standalone
    assert 'const target = returnTo || "/mini-app/?route=home";' in standalone
    assert "window.location.replace(target)" in standalone
    assert "STANDALONE_RETURNING_TO_KEY" in standalone
    assert "window.sessionStorage.setItem(STANDALONE_RETURNING_TO_KEY, target)" in standalone
    assert "safeMiniAppReferrer" in standalone
    assert "referrer.origin !== window.location.origin" in standalone
    assert 'path !== "/mini-app" && !path.startsWith("/mini-app/")' in standalone
    assert "window.history.back()" not in standalone
    assert '?route=catalog' not in standalone


def test_transient_layers_keep_first_back_press_for_local_close() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    assert "hasTransientCustomerLayer" in source
    assert '[role="dialog"]' in source
    assert '".sheet-overlay"' in source
    assert '".tiktok-sheet-layer"' in source
    assert "if (!isCustomerMainSurface() || hasTransientCustomerLayer()) return false;" in source
