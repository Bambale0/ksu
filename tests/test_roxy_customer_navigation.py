from pathlib import Path

from app.bot import keyboards
from app.core.config import settings


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_customer_navigation_has_approved_five_primary_routes() -> None:
    script = _read("roxy-customer-navigation.js")
    css = _read("roxy-customer-navigation.css")
    for route in ("home", "catalog", "create", "history", "profile"):
        assert f'"{route}"' in script
    for label in ("Главная", "Каталог", "Создать", "История", "Профиль"):
        assert label in script
    assert '["feed", "feed", "Лента"]' not in script
    assert 'feed: "feed"' in script  # legacy/deep route remains available
    assert 'catalog: "feed"' in script  # safe fallback if discovery layer cannot mount
    assert "RoxyDiscovery?.openCatalog" in script
    assert 'classList.contains("roxy-discovery-catalog-open")' in script
    assert 'wallet: "wallet"' in script  # secondary deep route, intentionally absent from primary nav
    assert 'new URLSearchParams(window.location.search).get("route")' in script
    assert "OPEN_ROUTES" in script
    assert "roxy-central-create" in script
    assert "<svg" in script
    assert "repeat(5" in css
    assert '[data-roxy-customer-route="feed"]' in css
    assert "display: none" in css
    assert "border-radius: 24px" in css
    assert "backdrop-filter" in css
    assert "#b184ff" in css
    assert "#ff69c9" in css
    assert ".roxy-central-create" in css


def test_roxy_brand_mounts_product_layers() -> None:
    brand = _read("roxy-brand.js")
    assert "function mountProductLayers()" in brand
    assert '/mini-app/roxy-customer-navigation.css' in brand
    assert '/mini-app/roxy-customer-navigation.js' in brand
    assert '/mini-app/roxy-discovery.css' in brand
    assert '/mini-app/roxy-discovery.js' in brand
    assert '/mini-app/roxy-approved-theme.css' in brand
    assert '/mini-app/roxy-approved-home.js' in brand
    assert '/mini-app/roxy-approved-surfaces.css' in brand
    assert "mountProductLayers();" in brand


def test_route_aware_mini_app_urls_are_used_by_minimal_bot_menu(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    menu = keyboards.main_menu()
    expected = [
        [("🚀 Открыть ROXY", "home")],
        [("✨ Создать", "create"), ("▦ Каталог", "catalog")],
        [("≡ История", "history"), ("👤 Профиль", "profile")],
    ]
    assert [len(row) for row in menu.inline_keyboard] == [1, 2, 2]
    for row, expected_row in zip(menu.inline_keyboard, expected, strict=True):
        assert len(row) == len(expected_row)
        for button, (label, route) in zip(row, expected_row, strict=True):
            assert button.text == label
            assert button.web_app is not None
            assert button.web_app.url == f"https://roxy.example/mini-app/?route={route}"
            assert button.callback_data is None

    payment_button = keyboards.balance_menu().inline_keyboard[0][0]
    assert payment_button.web_app is not None
    assert payment_button.web_app.url == "https://roxy.example/mini-app/?route=wallet"


def test_bot_menu_keeps_callback_fallbacks_without_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "")
    menu = keyboards.main_menu()
    callbacks = [[button.callback_data for button in row] for row in menu.inline_keyboard]
    assert callbacks == [
        ["nav:main"],
        ["create", "feed:open"],
        ["nav:main", "profile"],
    ]
    assert all(button.web_app is None for row in menu.inline_keyboard for button in row)
