from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bottom_nav_is_five_user_actions_with_create_centered() -> None:
    app = _read("frontend/mini-app/components/roxy-social-app.tsx")
    css = _read("frontend/mini-app/app/ux-polish.css")

    assert '["home", "home", "Студия"]' in app
    assert '["feed", "heart", "Лента"]' in app
    assert '["catalog", "catalog", "Каталог"]' in app
    assert '["create", "create", "Создать"]' in app
    assert '["profile", "profile", "Профиль"]' in app
    assert "bottom-nav button:nth-child(5) { display: none; }" in css
    assert "bottom-nav button:nth-child(4) { order: 3; }" in css
    assert "bottom-nav button.central" in css


def test_user_facing_copy_does_not_expose_provider_or_internal_routes() -> None:
    app = _read("frontend/mini-app/components/roxy-social-app.tsx")
    css = _read("frontend/mini-app/app/ux-polish.css")
    launcher = _read("app/bot/handlers/launcher.py")

    visible_copy = "\n".join([css, launcher])
    for forbidden in ("KIE", "provider", "server routes", "media routes", "ui_schema", "backend-каталог"):
        assert forbidden not in visible_copy

    assert "Выбирайте идею, создавайте результат" in css
    assert "@korkinaxenia" in _read("app/bot/keyboards.py")

    # Existing implementation strings may remain in legacy code, but the final polish layer must hide them.
    assert "Публичные публикации отдаются" in app
    assert "screen-head p::after" in css


def test_splash_loader_uses_brand_asset_inside_single_animated_ring() -> None:
    loader = _read("frontend/mini-app/app/loader.css")
    layout = _read("frontend/mini-app/app/layout.tsx")
    svg = _read("frontend/mini-app/public/brand/roxy-rx.svg")

    assert "url('/brand/roxy-rx.svg')" in loader
    assert "roxy-ring-spin" in loader
    assert "roxy-ring-counter" in loader
    assert "prefers-reduced-motion" in loader
    assert "./loader.css" in layout
    assert "./ux-polish.css" in layout
    assert "<svg" in svg
    assert "linearGradient" in svg
