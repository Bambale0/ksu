from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_customer_navigation_is_the_only_primary_menu_owner() -> None:
    navigation = _read("roxy-customer-navigation.js")
    economy = _read("roxy-economy.js")

    assert "root.replaceChildren(...MENU.map(menuButton))" in navigation
    assert "RoxyCustomerNavigation is the sole owner of visible primary menus" in economy
    assert "replaceChildren(...MENU.map(menuButton))" not in economy
    assert 'window.dispatchEvent(new CustomEvent("roxy:route-changed"' in navigation
    assert 'window.addEventListener("roxy:route-changed"' in economy


def test_customer_navigation_does_not_watch_the_whole_dom_tree() -> None:
    source = _read("roxy-customer-navigation.js")
    assert "bodyClassObserver.observe(document.body" in source
    observer_block = source.split("bodyClassObserver.observe(document.body", 1)[1].split("});", 1)[0]
    assert "subtree" not in observer_block
    assert "childList" not in observer_block
    assert 'attributeFilter: ["class"]' in observer_block


def test_economy_runtime_observers_are_scoped_to_owned_surfaces() -> None:
    source = _read("roxy-economy.js")
    assert "observe(document.body" not in source
    assert "state.contentObserver.observe(root" in source
    assert "state.routeObserver.observe(root" in source
    assert 'document.getElementById("walletView")' in source
    assert 'document.getElementById("partnerPreview")' in source
    assert 'attributeFilter: ["hidden"]' in source
