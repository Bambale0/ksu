from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_html_is_mobile_first_and_telegram_native() -> None:
    html = _read("index.html")
    assert 'name="viewport"' in html
    assert "width=device-width" in html
    assert "viewport-fit=cover" in html
    assert "https://telegram.org/js/telegram-web-app.js" in html


def test_mobile_runtime_is_mounted_after_product_layers() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-mobile-runtime.css' in brand
    assert '/mini-app/roxy-mobile-runtime.js' in brand
    assert brand.index('/mini-app/roxy-profile-cabinet.js') < brand.index('/mini-app/roxy-mobile-runtime.js')


def test_runtime_tracks_telegram_safe_area_and_stable_viewport() -> None:
    source = _read("roxy-mobile-runtime.js")
    for token in (
        "tg?.safeAreaInset",
        "tg?.contentSafeAreaInset",
        "tg?.viewportStableHeight",
        '"safeAreaChanged"',
        '"contentSafeAreaChanged"',
        '"viewportChanged"',
        '"--roxy-content-safe-bottom"',
        '"--roxy-stable-height"',
        "tg?.ready?.()",
        "tg?.expand?.()",
    ):
        assert token in source


def test_mobile_css_has_safe_area_fallbacks_and_five_item_bottom_navigation() -> None:
    base = _read("styles.css")
    studio = _read("studio-shell.css")
    mobile = _read("roxy-mobile-runtime.css")
    assert "--tg-viewport-stable-height" in base
    assert "--tg-content-safe-area-inset-bottom" in base
    assert "grid-template-columns: repeat(5" in studio
    for token in (
        "--roxy-content-safe-top",
        "--roxy-content-safe-right",
        "--roxy-content-safe-bottom",
        "--roxy-content-safe-left",
        "env(safe-area-inset-bottom, 0px)",
        "grid-template-columns: repeat(5",
        "overflow-x: hidden",
        "overflow-x: clip",
    ):
        assert token in mobile


def test_back_button_keeps_nested_shell_single_step_and_routes_top_level_back() -> None:
    runtime = _read("roxy-mobile-runtime.js")
    shell = _read("shell.js")
    navigation = _read("roxy-customer-navigation.js")

    assert "tg?.BackButton?.onClick?.(onBackButton)" in runtime
    assert "if (state.nestedVisible || nestedVisible()) return;" in runtime
    assert 'const feed = document.getElementById("feedOverlay")' in runtime
    assert "|| (feed && !feed.hidden)" in runtime
    assert 'window.RoxyCustomerNavigation?.open?.("profile", { feedback: false })' in runtime
    assert 'window.RoxyCustomerNavigation?.open?.("home", { feedback: false })' in runtime
    assert "if (visible) back.show();" in runtime
    assert "else back.hide();" in runtime

    # Existing shell remains owner of nested builder/result browser-history transitions.
    assert "tg?.BackButton?.onClick?.(() => closeNested())" in shell
    assert "history.back()" in shell

    # Startup deep routes remain bounded to the customer navigation allow-list.
    assert 'new URLSearchParams(window.location.search).get("route")' in navigation
    assert 'const OPEN_ROUTES = [...PRIMARY_ROUTES, "wallet"]' in navigation


def test_keyboard_runtime_handles_visual_viewport_and_ios_zoom() -> None:
    source = _read("roxy-mobile-runtime.js")
    css = _read("roxy-mobile-runtime.css")
    for token in (
        "window.visualViewport",
        "height >= 120",
        'document.body?.classList.toggle("roxy-keyboard-open", open)',
        "control.scrollIntoView({ block: \"center\", behavior: \"smooth\" })",
        "tg?.hideKeyboard?.()",
        'document.addEventListener("focusin", onFocusIn)',
    ):
        assert token in source
    assert ".roxy-keyboard-open .studio-bottom-nav" in css
    assert "pointer-events: none" in css
    assert "font-size: 16px" in css


def test_mobile_touch_targets_and_low_motion_fallbacks_are_explicit() -> None:
    source = _read("roxy-mobile-runtime.js")
    css = _read("roxy-mobile-runtime.css")
    assert 'String(tg?.platform || "").toLowerCase() === "android"' in source
    assert "navigator.hardwareConcurrency" in source
    assert 'document.documentElement.classList.toggle("roxy-low-motion"' in source
    assert "min-height: 44px" in css
    assert "touch-action: manipulation" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "backdrop-filter: none !important" in css


def test_catalog_feed_and_media_are_mobile_playback_safe() -> None:
    discovery = _read("roxy-discovery.js")
    discovery_css = _read("roxy-discovery.css")
    feed = _read("feed.js")
    shell = _read("shell.js")
    music = _read("roxy-music.js")
    mobile = _read("roxy-mobile-runtime.css")

    assert "scroll-snap-type: x mandatory" in discovery_css
    assert "overscroll-behavior-inline: contain" in discovery_css
    assert "video.playsInline = true" in discovery
    assert "video.preload = \"metadata\"" in discovery
    assert "media.controls = true" in feed
    assert "media.playsInline = true" in feed
    assert "video.controls = true" in shell
    assert "video.playsInline = true" in shell
    assert 'audio.className = "roxy-audio-player"' in music
    assert "audio.controls = true" in music
    assert ".roxy-audio-player" in mobile
    assert "touch-action: manipulation" in mobile


def test_checkout_opens_https_from_direct_user_activation_via_telegram() -> None:
    guard = _read("payment-link-guard.js")
    checkout = _read("primary-card-checkout.js")
    assert 'return parsed.protocol === "https:"' in guard
    assert "directUserActivation" in guard
    assert 'window.addEventListener("click", markActivation, true)' in guard
    assert 'typeof tg.openLink === "function"' in guard
    assert "if (tg?.openLink) tg.openLink(url);" in checkout
    assert 'window.open(url, "_blank", "noopener,noreferrer")' in checkout
