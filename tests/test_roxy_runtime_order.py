from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_functional_runtime_executes_before_legacy_app_shell() -> None:
    html = (MINI / "index.html").read_text(encoding="utf-8")
    assert html.index('/mini-app/roxy-functional-runtime.js') < html.index('/mini-app/app.js')
    assert html.index('/mini-app/roxy-functional-runtime.js') < html.index('/mini-app/shell.js')


def test_top_level_roxy_popstate_is_owned_by_canonical_router() -> None:
    runtime = (MINI / "roxy-functional-runtime.js").read_text(encoding="utf-8")
    assert "function protectCanonicalPopState()" in runtime
    assert "event.state?.roxyNavigation" in runtime
    assert "event.stopImmediatePropagation()" in runtime
    assert 'historyMode: "none"' in runtime
    assert runtime.index("protectCanonicalPopState();") < runtime.index('if (document.readyState === "loading")')


def test_visible_legacy_chrome_and_tools_are_routed_through_roxy_history() -> None:
    runtime = (MINI / "roxy-functional-runtime.js").read_text(encoding="utf-8")
    for token in (
        "#brandHomeButton",
        "#productHeader [data-shell-nav]",
        "#createHome [data-shell-nav]",
        "#roxyHomeTools .roxy-home-tool",
        ".studio-sidebar-secondary [data-studio-secondary]",
        "routeTrustedLegacyChrome",
        "routeCustomerControl",
        "window.RoxyCustomerNavigation.open(route)",
    ):
        assert token in runtime
