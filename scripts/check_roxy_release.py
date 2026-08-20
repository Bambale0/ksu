from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"

TARGET_VIEWPORTS = (
    (360, 800),
    (390, 844),
    (430, 932),
    (1366, 768),
    (1920, 1080),
)

REQUIRED_ASSETS = (
    "index.html",
    "roxy-brand.js",
    "roxy-brand.css",
    "roxy-design-system.css",
    "roxy-icons.js",
    "roxy-customer-navigation.js",
    "roxy-child-screens.js",
    "roxy-mobile-runtime.js",
    "roxy-functional-runtime.js",
    "feed.js",
    "trends.js",
    "prompt-tools.js",
    "roxy-music.js",
)

# These modules are retained as low-level compatibility implementations for existing
# shell/payment flows. They may still contain historical source literals, but their
# rendered text is normalized by roxy-approved-home.js before it remains visible.
# New/canonical customer surfaces are never exempt from the release copy gate.
LEGACY_COMPAT_SOURCES = {
    "app.js",
    "primary-card-checkout.js",
    "shell.js",
    "studio-shell.js",
    "wallet.js",
}

RETIRED_VISUAL_LAYERS = (
    "roxy-approved-theme.css",
    "roxy-approved-surfaces.css",
    "roxy-client-feedback.css",
    "roxy-unified-controls.css",
    "roxy-iphone-polish.css",
    "roxy-fhd-density.css",
    "roxy-home-density-v3.css",
    "roxy-mature-ui.css",
    "roxy-mobile-runtime.css",
    "roxy-header-logo.css",
)


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def validate() -> list[str]:
    errors: list[str] = []

    for name in REQUIRED_ASSETS:
        path = MINI / name
        if not path.is_file() or path.stat().st_size < 80:
            errors.append(f"missing-or-empty:{name}")

    for name in RETIRED_VISUAL_LAYERS:
        if (MINI / name).exists():
            errors.append(f"retired-visual-layer-present:{name}")

    if errors:
        return errors

    index = _read("index.html")
    brand = _read("roxy-brand.js")
    brand_entry = _read("roxy-brand.css")
    design = _read("roxy-design-system.css")
    icons = _read("roxy-icons.js")
    nav = _read("roxy-customer-navigation.js")
    children = _read("roxy-child-screens.js")
    mobile_js = _read("roxy-mobile-runtime.js")
    functional_js = _read("roxy-functional-runtime.js")
    feed = _read("feed.js")
    social = _read("social.js")
    economy = _read("roxy-economy.js")
    music = _read("roxy-music.js")
    approved_home = _read("roxy-approved-home.js")

    if "viewport-fit=cover" not in index:
        errors.append("viewport-fit-cover")
    if "https://telegram.org/js/telegram-web-app.js" not in index:
        errors.append("telegram-webapp-sdk")

    if '@import url("/mini-app/roxy-design-system.css?v=1")' not in brand_entry:
        errors.append("brand-entrypoint-canonical-design")
    if '/mini-app/roxy-design-system.css?v=1' not in brand:
        errors.append("canonical-design-runtime")
    for retired in RETIRED_VISUAL_LAYERS:
        if f"/mini-app/{retired}" in brand:
            errors.append(f"retired-visual-runtime:{retired}")

    for token in ("#0b0b10", "#9b5cff", "#ff5fb7", "#ffffff", "#a6a6b3"):
        if token not in design.lower():
            errors.append(f"palette:{token}")
    for token in (
        ":focus-visible",
        "prefers-reduced-motion: reduce",
        "min-height: 44px",
        "touch-action: manipulation",
        "grid-template-columns: repeat(5",
        "--tg-content-safe-area-inset-bottom",
        "@media (max-width: 430px)",
        ".roxy-approved-hero",
        ".roxy-media-card",
        ".studio-result-pane",
        ".roxy-audio-player",
        ".studio-library-grid",
        ".roxy-cabinet-action",
        ".studio-bottom-nav",
        ".payment-package",
        ".feed-card",
    ):
        if token not in design:
            errors.append(f"design-system:{token}")

    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e"):
        if legacy_gold in design.lower():
            errors.append(f"legacy-palette:{legacy_gold}")

    for name, source in (("brand", brand), ("economy", economy)):
        if "createTreeWalker" in source or "TreeWalker" in source:
            errors.append(f"global-text-scan:{name}")
    if "MutationObserver" in brand:
        errors.append("brand-global-observer")
    for name, source in (("feed", feed), ("social", social)):
        if "window.fetch =" in source or "originalFetch" in source:
            errors.append(f"fetch-monkeypatch:{name}")

    if "observe(document.body" in economy:
        errors.append("economy-body-observer")
    if "observe(document.body" in music:
        errors.append("music-body-observer")

    expected_children = {
        "notifications": "profile",
        "support": "profile",
        "creator": "profile",
        "subscriptions": "profile",
        "author": "profile",
        "references": "create",
        "presets": "create",
        "batch": "create",
        "trends": "catalog",
        '"prompt-tools"': "catalog",
    }
    for route, parent in expected_children.items():
        token = f"{route}: \"{parent}\""
        if token not in nav:
            errors.append(f"child-route:{route}")

    for route in (
        "notifications",
        "support",
        "creator",
        "subscriptions",
        "author",
        "references",
        "presets",
        "batch",
        "trends",
    ):
        if f"{route}:" not in children:
            errors.append(f"child-screen:{route}")
    if '"prompt-tools":' not in children:
        errors.append("child-screen:prompt-tools")

    if "window.RoxyIcons?.create?." not in nav:
        errors.append("nav-svg-icons")
    if "innerHTML" in icons or "insertAdjacentHTML" in icons:
        errors.append("icon-html-injection")
    if "document.createElementNS" not in icons:
        errors.append("icon-svg-runtime")

    for token in (
        "window.visualViewport",
        "tg?.safeAreaInset",
        "tg?.contentSafeAreaInset",
        "tg?.BackButton?.onClick?.(onBackButton)",
        "window.history.back()",
    ):
        if token not in mobile_js:
            errors.append(f"mobile-runtime:{token}")

    for token in (
        "installRandomUuidFallback()",
        "protectCanonicalHistory()",
        "observeNotificationSemantics()",
        "nativeReplaceState(data, title, url)",
        "current?.roxyNavigation",
        "button.disabled = !unread",
        "navigator.clipboard?.writeText",
        'document.execCommand("copy")',
    ):
        if token not in functional_js:
            errors.append(f"functional-runtime:{token}")

    # Compatibility source exemptions are only safe while the approved runtime owns
    # both old brand-name fallbacks and historical credit labels in rendered DOM text.
    for token in (
        "LEGACY_BRAND_RE",
        "normalizeCopyString",
        "normalizeVisibleCopy(document.body)",
        "MutationObserver",
        '"ROXY"',
        '"$1 ROX"',
    ):
        if token not in approved_home:
            errors.append(f"compat-copy-normalizer:{token}")

    legacy_offenders: list[str] = []
    for path in MINI.iterdir():
        if path.suffix not in {".js", ".html", ".css"}:
            continue
        if path.name in LEGACY_COMPAT_SOURCES:
            continue
        source = path.read_text(encoding="utf-8")
        if "Ксю" in source or "КСЮ" in source or " кр." in source:
            legacy_offenders.append(path.name)
    if legacy_offenders:
        errors.append("legacy-copy:" + ",".join(sorted(legacy_offenders)))

    for legacy_page, route in (
        ("trends.html", "trends"),
        ("prompt-tools.html", "prompt-tools"),
        ("batch.html", "batch"),
    ):
        source = _read(legacy_page)
        if "/mini-app/roxy-legacy-route-redirect.js" not in source or f'data-roxy-route="{route}"' not in source:
            errors.append(f"legacy-forward:{legacy_page}")

    if len(TARGET_VIEWPORTS) != 5 or TARGET_VIEWPORTS[-1] != (1920, 1080):
        errors.append("viewport-matrix")

    return errors


def main() -> int:
    errors = validate()
    print("ROXY release target viewports:")
    for width, height in TARGET_VIEWPORTS:
        print(f"  - {width}x{height}")
    if errors:
        print("ROXY release gate FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("ROXY release gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
