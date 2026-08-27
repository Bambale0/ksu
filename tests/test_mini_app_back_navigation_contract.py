from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
ENTRY = ROOT / "frontend" / "mini-app" / "components" / "app-entry-gate.tsx"
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
    assert "BackButton?: BackButton;" in source
