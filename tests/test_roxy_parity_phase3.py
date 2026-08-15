from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_native_child_screen_router_reuses_existing_live_components() -> None:
    source = _read("roxy-child-screens.js")
    for route, selector in (
        ("notifications", "#profileNotificationList"),
        ("support", "#supportComposeForm"),
        ("creator", "#creatorPartnershipEntry"),
        ("subscriptions", ".social-profile-section"),
    ):
        assert f"{route}:" in source
        assert f'selector: "{selector}"' in source
    assert "roxy-child-screen-placeholder" in source
    assert "restoreMovedTarget" in source
    assert "#appMain > .app-view" in source
    assert "fetch(" not in source


def test_library_and_batch_are_native_child_routes_not_duplicate_api_clients() -> None:
    children = _read("roxy-child-screens.js")
    batch = _read("roxy-batch-embedded.js")
    assert 'libraryTab: "references"' in children
    assert 'libraryTab: "presets"' in children
    assert "window.KsuStudioShell?.openLibrary?.(config.libraryTab)" in children
    assert 'window.RoxyBatchEmbedded.open({ manageHistory: false })' in children
    assert "function open({ manageHistory = true } = {})" in batch
    assert 'history.state?.route === "batch"' in batch
    assert "close: ({ historyBack = state.manageHistory } = {})" in batch


def test_trends_and_prompt_tools_reuse_the_existing_runtime_inside_the_shell() -> None:
    children = _read("roxy-child-screens.js")
    trends = _read("trends.js")
    for token in (
        'legacyApp: "trends"',
        'legacyApp: "prompt-tools"',
        'css: "/mini-app/trends.css"',
        'script: "/mini-app/trends.js"',
        'css: "/mini-app/prompt-tools.css"',
        'script: "/mini-app/prompt-tools.js"',
        'root.id = "trendsApp"',
        'root.id = "promptToolsApp"',
    ):
        assert token in children
    assert 'window.history.replaceState({ ...(window.history.state || {}) }, "", url)' in trends
    assert 'url.searchParams.set("trend", item.id)' in trends
    assert 'url.searchParams.delete("trend")' in trends


def test_primary_router_accepts_child_routes_and_maps_them_to_parent_navigation() -> None:
    navigation = _read("roxy-customer-navigation.js")
    for token in (
        'notifications: "profile"',
        'support: "profile"',
        'creator: "profile"',
        'subscriptions: "profile"',
        'references: "create"',
        'presets: "create"',
        'batch: "create"',
        'trends: "catalog"',
        '"prompt-tools": "catalog"',
        'const OPEN_ROUTES = [...PRIMARY_ROUTES, "wallet", ...CHILD_ROUTES]',
        "window.RoxyChildScreens?.open?.(route)",
        "window.RoxyChildScreens?.close?.()",
    ):
        assert token in navigation


def test_home_and_profile_tool_cards_use_canonical_child_routes() -> None:
    source = _read("roxy-parity-navigation.js")
    for route in (
        "notifications",
        "support",
        "subscriptions",
        "creator",
        "batch",
        "trends",
        "prompt-tools",
    ):
        assert f'openRoute("{route}")' in source
    assert 'openLibrary("references")' in source
    assert 'openLibrary("presets")' in source
    assert "fetch(" not in source


def test_child_screen_intercepts_legacy_standalone_links() -> None:
    source = _read("roxy-child-screens.js")
    for path, route in (
        ("/mini-app/trends.html", "trends"),
        ("/mini-app/prompt-tools.html", "prompt-tools"),
        ("/mini-app/batch.html", "batch"),
    ):
        assert path in source
        assert f'? "{route}"' in source or f': "{route}"' in source
    assert "event.preventDefault()" in source
    assert "window.RoxyCustomerNavigation?.open?.(route)" in source


def test_child_screen_assets_are_mounted_before_customer_navigation() -> None:
    brand = _read("roxy-brand.js")
    css = _read("roxy-child-screens.css")
    assert '/mini-app/roxy-child-screens.css' in brand
    assert '/mini-app/roxy-child-screens.js' in brand
    assert brand.index('/mini-app/roxy-child-screens.js') < brand.index('/mini-app/roxy-customer-navigation.js')
    assert ".roxy-child-screen[hidden]" in css
    assert ".roxy-child-screen-back" in css
