from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_brand_runtime_never_rescans_full_body_for_dynamic_text_updates() -> None:
    source = _read("roxy-brand.js")
    assert "MutationObserver" not in source
    assert "createTreeWalker" not in source
    assert "document.body, { childList: true, subtree: true }" not in source
    assert "function refreshBrandChrome()" in source
    assert "function scheduleRefreshes()" in source
    assert "window.addEventListener(\"roxy:route-changed\", refreshBrandChrome)" in source
    assert "window.addEventListener(\"roxy:shell-route-changed\", refreshBrandChrome)" in source


def test_mobile_runtime_filters_and_coalesces_global_mutation_work() -> None:
    source = _read("roxy-mobile-runtime.js")
    assert "function mutationAffectsNavigation(mutation)" in source
    assert "if (!mutations.some(mutationAffectsNavigation)) return;" in source
    assert "function scheduleBackSync()" in source
    assert "if (state.backFrame) return;" in source
    assert "scheduleBackSync();" in source


def test_canonical_design_has_reduced_motion_and_bounded_glass_surfaces() -> None:
    css = _read("roxy-design-system.css")
    assert "prefers-reduced-motion: reduce" in css
    assert "backdrop-filter: blur(20px)" in css
    assert "backdrop-filter: blur(22px)" in css
    assert "position: fixed" in css
    assert ".studio-bottom-nav" in css
