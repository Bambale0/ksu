from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_primary_navigation_uses_semantic_svg_icons_not_text_glyphs() -> None:
    source = _read("roxy-customer-navigation.js")
    assert 'window.RoxyIcons?.create?.(name, { size: 21 })' in source
    for token in (
        '["home", "home", "Главная"]',
        '["catalog", "catalog", "Каталог"]',
        '["create", "create", "Создать"]',
        '["history", "history", "История"]',
        '["profile", "profile", "Профиль"]',
    ):
        assert token in source
    for glyph in ("⌂", "▦", "＋", "≡", "○"):
        assert glyph not in source


def test_home_and_profile_tools_use_the_shared_icon_system() -> None:
    source = _read("roxy-parity-navigation.js")
    assert 'window.RoxyIcons?.create?.(name, { size: 22 })' in source
    for icon_name in (
        "catalog",
        "feed",
        "trend",
        "prompt",
        "batch",
        "image",
        "bell",
        "support",
        "users",
        "creator",
        "settings",
    ):
        assert f'"{icon_name}"' in source
    for legacy in ("🔔", "💬", "👤", "👥", "⚙", "🎟"):
        assert legacy not in source


def test_feed_actions_are_semantic_and_icon_driven() -> None:
    source = _read("feed.js")
    assert "function iconAction(" in source
    assert "window.RoxyIcons?.create?.(iconName" in source
    assert "button.dataset.feedAction = actionName" in source
    for action_name in ("like", "comments", "share", "remix", "author", "profile", "post-link"):
        assert f'"{action_name}"' in source
    for legacy in ("👤 Автор", "👤 Профиль", "🔁 Повторить", "🌐 В ленту", "🆕 Новые"):
        assert legacy not in source


def test_trends_and_prompt_tools_use_rox_source_copy() -> None:
    for name in ("trends.js", "prompt-tools.js"):
        source = _read(name)
        assert " ROX" in source
        assert " кр." not in source
        assert "Ксю" not in source
    assert "Недостаточно ROX" in _read("trends.js")
    assert "Недостаточно ROX" in _read("prompt-tools.js")


def test_brand_and_economy_do_not_rewrite_arbitrary_dom_text() -> None:
    for name in ("roxy-brand.js", "roxy-economy.js"):
        source = _read(name)
        assert "createTreeWalker" not in source
        assert "TreeWalker" not in source
    brand = _read("roxy-brand.js")
    economy = _read("roxy-economy.js")
    assert "MutationObserver" not in brand
    assert "rewritePartnerCurrency" not in economy
    assert "rewriteWalletCreditCopy" not in economy


def test_concept_one_visual_layer_is_last_and_motion_is_restrained() -> None:
    brand = _read("roxy-brand.js")
    css = _read("roxy-design-system.css")
    assert '/mini-app/roxy-mature-ui.css' not in brand
    assert '/mini-app/roxy-mobile-runtime.css' not in brand
    assert brand.rindex('/mini-app/roxy-design-system.css?v=1') > brand.index('/mini-app/roxy-app-onboarding.css?v=1')
    assert "--roxy-radius-sm: 13px" in css
    assert "--roxy-radius-md: 18px" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "body::before" in css
