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
    assert 'feed: "feed"' in script
    assert 'catalog: "feed"' in script
    assert "RoxyDiscovery?.openCatalog" in script
    assert 'classList.contains("roxy-discovery-catalog-open")' in script
    assert 'wallet: "wallet"' in script
    assert 'new URLSearchParams(window.location.search).get("route")' in script
    assert "OPEN_ROUTES" in script
    assert "roxy-central-create" in script
    assert 'window.RoxyIcons?.create?.(name, { size: 21 })' in script
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
    assert '/mini-app/roxy-icons.js' in brand
    assert '/mini-app/roxy-customer-navigation.css' in brand
    assert '/mini-app/roxy-customer-navigation.js' in brand
    assert '/mini-app/roxy-discovery.css' in brand
    assert '/mini-app/roxy-discovery.js' in brand
    assert '/mini-app/roxy-approved-theme.css' in brand
    assert '/mini-app/roxy-approved-home.js' in brand
    assert '/mini-app/roxy-approved-surfaces.css' in brand
    assert '/mini-app/roxy-client-feedback.css' in brand
    assert brand.index('/mini-app/roxy-client-feedback.css') > brand.index('/mini-app/roxy-approved-surfaces.css')
    assert "mountProductLayers();" in brand


def test_telegram_launcher_opens_only_roxy_mini_app(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    menu = keyboards.main_menu()
    assert len(menu.inline_keyboard) == 1
    assert len(menu.inline_keyboard[0]) == 1
    button = menu.inline_keyboard[0][0]
    assert button.text == "🚀 Открыть ROXY"
    assert button.web_app is not None
    assert button.web_app.url == "https://roxy.example/mini-app/?route=home"
    assert button.callback_data is None

    payment_button = keyboards.balance_menu().inline_keyboard[0][0]
    assert payment_button.web_app is not None
    assert payment_button.web_app.url == "https://roxy.example/mini-app/?route=wallet"


def test_bot_launcher_keeps_single_safe_fallback_without_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "")
    menu = keyboards.main_menu()
    assert len(menu.inline_keyboard) == 1
    assert len(menu.inline_keyboard[0]) == 1
    button = menu.inline_keyboard[0][0]
    assert button.text == "🚀 Открыть ROXY"
    assert button.callback_data == "nav:main"
    assert button.web_app is None


def test_persistent_quick_menu_has_exact_two_primary_buttons() -> None:
    menu = keyboards.quick_menu()
    assert menu.is_persistent is True
    assert menu.resize_keyboard is True
    assert [[button.text for button in row] for row in menu.keyboard] == [
        ["🏠 Меню", "🆘 Поддержка"]
    ]
