from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "frontend" / "mini-app"


def test_prompt_tools_expose_webview_safe_copy_actions_for_ready_prompts() -> None:
    page = (MINI / "app" / "prompt-tools" / "page.tsx").read_text(encoding="utf-8")
    telegram = (MINI / "lib" / "telegram.ts").read_text(encoding="utf-8")

    assert 'copyToClipboard, haptic, notify' in page
    assert 'label === "Промпт RU" || label === "Промпт EN"' in page
    assert 'aria-label={`Скопировать ${label}`}' in page
    assert 'copiedLabel === label ? "Скопировано ✓" : "Копировать"' in page
    assert 'await copyToClipboard(value)' in page
    assert 'notify("success")' in page
    assert 'haptic("light")' in page

    # Prompt Tools must reuse the shared Telegram/WebView-safe fallback instead
    # of calling the Clipboard API directly from the feature screen.
    assert "navigator.clipboard" not in page
    assert "navigator.clipboard?.writeText" in telegram
    assert 'document.execCommand("copy")' in telegram
