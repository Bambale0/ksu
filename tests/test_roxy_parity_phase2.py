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


def test_economy_content_mutations_cannot_trigger_an_api_refresh_loop() -> None:
    source = _read("roxy-economy.js")
    apply_block = source.split("function apply()", 1)[1].split("function scheduleApply()", 1)[0]
    assert "loadStats" not in apply_block
    assert "function routeMutation(mutations)" in source
    assert 'mutation.target?.id === "walletView" && !mutation.target.hidden' in source


def test_music_runtime_observer_is_scoped_to_music_and_generation_surfaces() -> None:
    source = _read("roxy-music.js")
    assert "observe(document.body" not in source
    assert "state.contentObserver.observe(root" in source
    for node_id in (
        "roxyCreateCenterView",
        "createHome",
        "builderView",
        "resultCard",
        "generationDetailView",
        "ksuHistoryOverlay",
    ):
        assert f'document.getElementById("{node_id}")' in source
    assert 'window.addEventListener("roxy:route-changed", scheduleApply)' in source


def test_generation_context_replaces_global_fetch_interception() -> None:
    context = _read("roxy-generation-context.js")
    social = _read("social.js")
    feed = _read("feed.js")
    brand = _read("roxy-brand.js")

    assert 'emit("roxy:history-context"' in context
    assert 'emit("roxy:generation-context"' in context
    assert 'state.historyObserver.observe(root, { childList: true })' in context
    assert 'attributeFilter: ["hidden"]' in context
    assert 'mountLayer({ js: "/mini-app/roxy-generation-context.js" })' in brand

    for source in (social, feed):
        assert "window.fetch =" not in source
        assert "originalFetch" not in source
        assert 'window.addEventListener("roxy:generation-context"' in source
    assert 'window.addEventListener("roxy:history-context"' in social


def test_mobile_navigation_observation_is_top_level_and_surface_scoped() -> None:
    source = _read("roxy-mobile-runtime.js")
    assert "state.bodyObserver.observe(document.body" in source
    body_block = source.split("state.bodyObserver.observe(document.body", 1)[1].split("});", 1)[0]
    assert "subtree" not in body_block
    assert "childList: true" in body_block
    assert 'attributeFilter: ["class"]' in body_block
    assert "state.surfaceObserver.observe(root" in source
    assert 'root.tagName === "DIALOG" ? ["open"] : ["hidden"]' in source
