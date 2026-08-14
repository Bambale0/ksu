from pathlib import Path

from app.bot import keyboards
from app.core.config import settings


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_customer_navigation_has_approved_primary_routes_and_central_create() -> None:
    script = _read("roxy-customer-navigation.js")
    css = _read("roxy-customer-navigation.css")
    for route in ("home", "catalog", "create", "history", "profile"):
        assert f'"{route}"' in script
    for label in ("Главная", "Каталог", "Создать", "История", "Профиль"):
        assert label in script
    assert 'catalog: "feed"' in script  # transitional until Catalog epic replaces the backing surface
    assert 'new URLSearchParams(window.location.search).get("route")' in script
    assert "roxy-central-create" in script
    assert ".roxy-central-create" in css
    assert "--tg-content-safe-area" not in css  # inherited from the existing Studio nav shell


def test_roxy_brand_mounts_customer_navigation_layer() -> None:
    brand = _read("roxy-brand.js")
    assert "function mountCustomerNavigation()" in brand
    assert '/mini-app/roxy-customer-navigation.css' in brand
    assert '/mini-app/roxy-customer-navigation.js' in brand
    assert "mountCustomerNavigation();" in brand


def test_route_aware_mini_app_urls_are_used_by_bot_menu(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    menu = keyboards.main_menu()
    expected = [
        ("🏠 Главная", "home"),
        ("▦ Каталог", "catalog"),
        ("✨ Создать", "create"),
        ("≡ История", "history"),
        ("👤 Профиль", "profile"),
    ]
    assert len(menu.inline_keyboard) == len(expected)
    for row, (label, route) in zip(menu.inline_keyboard, expected, strict=True):
        button = row[0]
        assert button.text == label
        assert button.web_app is not None
        assert button.web_app.url == f"https://roxy.example/mini-app/?route={route}"
        assert button.callback_data is None


def test_bot_menu_keeps_callback_fallbacks_without_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "")
    menu = keyboards.main_menu()
    callbacks = [row[0].callback_data for row in menu.inline_keyboard]
    assert callbacks == ["nav:main", "feed:open", "create", "nav:main", "profile"]
