from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
ENTRY = ROOT / "frontend" / "mini-app" / "components" / "app-entry-gate.tsx"
SOCIAL_APP = ROOT / "frontend" / "mini-app" / "components" / "roxy-social-app.tsx"
TELEGRAM = ROOT / "frontend" / "mini-app" / "lib" / "telegram.ts"


def test_root_does_not_mount_duplicate_in_app_back_button() -> None:
    page = PAGE.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    assert "UniversalBackButton" not in page
    assert "data-roxy-back-button" not in page
    assert 'import { AppEntryGate } from "@/components/app-entry-gate";' in page
    assert "<GenerationActionGate />" in entry
    assert "<FeedStartApp {...target} />" not in entry
    assert "generationId={target.generationId}" in entry
    assert "referralCode={target.referralCode}" in entry
    assert "intent={target.kind}" in entry


def test_telegram_webview_back_button_contract_remains_available() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    assert "type BackButton = {" in source
    assert "show?: () => void;" in source
    assert "hide?: () => void;" in source
    assert "onClick?: (callback: () => void) => void;" in source
    assert "offClick?: (callback: () => void) => void;" in source
    assert "BackButton?: BackButton;" in source


def test_catalog_uses_native_close_chrome_while_other_customer_routes_keep_back() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    init = source.split("export function initTelegram()", 1)[1].split("function safeAreaValue", 1)[0]

    assert "tg.BackButton?.hide?.();" in init
    assert "Telegram's own Close affordance visible" in init
    assert "function shouldUseTelegramCloseChrome(): boolean" in source
    assert 'currentMainRoute() === "catalog"' in source
    assert "&& !hasTransientCustomerLayer();" in source
    assert "if (shouldUseTelegramCloseChrome()) rawHide?.();" in source
    assert "else if (isMainMiniAppPath()) rawShow?.();" in source
    assert "tg.close?.();" not in init


def test_main_menu_delegates_back_to_managed_webview_history() -> None:
    social = SOCIAL_APP.read_text(encoding="utf-8")
    telegram = TELEGRAM.read_text(encoding="utf-8")

    # Local surfaces still own their first Back press (preview/wallet), while
    # the shared Telegram adapter owns route history and closing at Home.
    assert 'if (preview || walletOpen || route !== "home") tg.BackButton.show?.();' in social
    assert "else tg.BackButton.hide?.();" in social
    assert "tg.BackButton.onClick?.(back);" in social
    assert "tg.BackButton?.offClick?.(back);" in social
    assert "if (!handleCustomerBack(tg)) callback();" in telegram
    assert "window.history.back();" in telegram
    assert "tg.close?.();" in telegram
