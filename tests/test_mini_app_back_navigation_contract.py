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


def test_telegram_initialization_resets_to_native_close_chrome() -> None:
    source = TELEGRAM.read_text(encoding="utf-8")
    init = source.split("export function initTelegram()", 1)[1].split("function safeAreaValue", 1)[0]

    assert "tg.BackButton?.hide?.();" in init
    assert "Nested screens explicitly opt back in with BackButton.show()." in init
    assert "tg.close?.();" not in init


def test_main_menu_hides_back_while_nested_surfaces_show_it() -> None:
    source = SOCIAL_APP.read_text(encoding="utf-8")

    assert 'if (preview || walletOpen || route !== "home") tg.BackButton.show?.();' in source
    assert "else tg.BackButton.hide?.();" in source
    assert "tg.BackButton.onClick?.(back);" in source
    assert "tg.BackButton?.offClick?.(back);" in source
