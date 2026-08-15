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
    "roxy-icons.js",
    "roxy-mature-ui.css",
    "roxy-customer-navigation.js",
    "roxy-child-screens.js",
    "roxy-mobile-runtime.js",
    "roxy-mobile-runtime.css",
    "roxy-fhd-density.css",
    "feed.js",
    "trends.js",
    "prompt-tools.js",
)


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def validate() -> list[str]:
    errors: list[str] = []

    for name in REQUIRED_ASSETS:
        path = MINI / name
        if not path.is_file() or path.stat().st_size < 80:
            errors.append(f"missing-or-empty:{name}")

    if errors:
        return errors

    index = _read("index.html")
    brand = _read("roxy-brand.js")
    icons = _read("roxy-icons.js")
    mature = _read("roxy-mature-ui.css")
    nav = _read("roxy-customer-navigation.js")
    children = _read("roxy-child-screens.js")
    mobile_js = _read("roxy-mobile-runtime.js")
    mobile_css = _read("roxy-mobile-runtime.css")
    fhd = _read("roxy-fhd-density.css")
    feed = _read("feed.js")
    social = _read("social.js")
    economy = _read("roxy-economy.js")
    music = _read("roxy-music.js")

    if "viewport-fit=cover" not in index:
        errors.append("viewport-fit-cover")
    if "https://telegram.org/js/telegram-web-app.js" not in index:
        errors.append("telegram-webapp-sdk")

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

    for route in ("notifications", "support", "creator", "subscriptions", "author", "references", "presets", "batch", "trends"):
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
        "--roxy-radius: 12px",
        "--roxy-radius-small: 9px",
        "opacity: .18",
        ":focus-visible",
        "prefers-reduced-motion: reduce",
    ):
        if token not in mature:
            errors.append(f"mature-ui:{token}")

    for token in (
        "env(safe-area-inset-bottom, 0px)",
        "font-size: 16px",
        "min-height: 44px",
        "overflow-x: hidden",
        "overflow-x: clip",
    ):
        if token not in mobile_css:
            errors.append(f"mobile-css:{token}")
    for token in (
        "window.visualViewport",
        "tg?.safeAreaInset",
        "tg?.contentSafeAreaInset",
        "tg?.BackButton?.onClick?.(onBackButton)",
        "window.history.back()",
    ):
        if token not in mobile_js:
            errors.append(f"mobile-runtime:{token}")

    if "1920" not in fhd and "min-width" not in fhd:
        errors.append("fhd-density-contract")

    legacy_offenders: list[str] = []
    for path in MINI.iterdir():
        if path.suffix not in {".js", ".html", ".css"}:
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
