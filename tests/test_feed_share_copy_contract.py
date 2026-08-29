from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "frontend" / "mini-app" / "app" / "layout.tsx"
SCRIPT = ROOT / "frontend" / "mini-app" / "public" / "share-copy-ux.js"


def test_share_copy_ux_is_loaded_by_mini_app() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    assert 'src="/mini-app/share-copy-ux.js"' in layout
    assert 'strategy="afterInteractive"' in layout


def test_telegram_share_exposes_direct_copy_link_action() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert '"/share/url"' in script
    assert "Скопировать ссылку" in script
    assert "Поделиться в Telegram" in script
    assert "navigator.clipboard?.writeText" in script
    assert 'document.execCommand("copy")' in script
    assert "originalOpenTelegramLink(rawUrl)" in script
    assert 'root.setAttribute("aria-label", title)' in script
    assert 'return "Поделиться работой"' in script
    assert 'return "Поделиться трендом"' in script
    assert "Ссылка скопирована ✓" in script
