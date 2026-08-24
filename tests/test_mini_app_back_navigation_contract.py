from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
ENTRY = ROOT / "frontend" / "mini-app" / "components" / "app-entry-gate.tsx"
BACK = ROOT / "frontend" / "mini-app" / "components" / "universal-back-button.tsx"


def test_universal_back_button_is_mounted_above_route_gate() -> None:
    page = PAGE.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    assert 'import { UniversalBackButton } from "@/components/universal-back-button";' in page
    assert 'import { AppEntryGate } from "@/components/app-entry-gate";' in page
    assert page.index("<UniversalBackButton />") < page.index("<AppEntryGate />")
    assert "<GenerationActionGate />" in entry
    assert "<FeedStartApp {...target} />" not in entry
    assert "generationId={target.generationId}" in entry
    assert "referralCode={target.referralCode}" in entry
    assert "intent={target.kind}" in entry


def test_back_button_is_injected_into_every_rendered_screen() -> None:
    source = BACK.read_text(encoding="utf-8")
    assert 'document.querySelector<HTMLElement>(".main-shell .screen")' in source
    assert "screen.prepend(nextHost)" in source
    assert "data-roxy-back-button" in source
    assert "<span>Назад</span>" in source


def test_back_button_handles_history_deep_links_actions_and_root_exit() -> None:
    source = BACK.read_text(encoding="utf-8")
    assert 'activeRoute === "generation-action"' in source
    assert 'url.searchParams.set("route", "history")' in source
    assert 'url.searchParams.set("route", "home")' in source
    assert "window.history.back()" in source
    assert "tg?.close" in source
    assert "tg.close()" in source
