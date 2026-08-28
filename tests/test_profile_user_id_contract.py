from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "frontend" / "mini-app" / "app" / "layout.tsx"
SCRIPT = ROOT / "frontend" / "mini-app" / "public" / "profile-id-ux.js"


def test_main_profile_loads_user_id_enhancer() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    assert '<Script src="/mini-app/profile-id-ux.js" strategy="afterInteractive" />' in layout


def test_profile_user_id_comes_from_current_telegram_user() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "initDataUnsafe?.user?.id" in script
    assert 'document.querySelectorAll(".profile-screen .profile-copy")' in script
    assert "`ID ${id}`" in script
    assert "Telegram ID ${id}" in script


def test_profile_user_id_survives_client_side_route_changes_without_duplicates() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'const MARK_ATTR = "data-roxy-profile-user-id"' in script
    assert "new MutationObserver" in script
    assert 'profileCopy.querySelector(`[${MARK_ATTR}]`)' in script
    assert 'label.setAttribute(MARK_ATTR, "")' in script


def test_profile_user_id_observer_does_not_mutate_the_same_text_forever() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "if (label.textContent !== text) label.textContent = text;" in script
    assert 'if (label.getAttribute("aria-label") !== accessibleText)' in script
    assert 'if (label.getAttribute("title") !== accessibleText)' in script
