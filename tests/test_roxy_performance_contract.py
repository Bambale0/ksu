from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_brand_runtime_never_rescans_full_body_for_dynamic_text_updates() -> None:
    source = _read("roxy-brand.js")
    assert "pendingBrandRoots" in source
    assert "observer = new MutationObserver(scheduleDynamicBranding)" in source
    assert "observer.observe(document.body, { childList: true, subtree: true });" in source
    assert "for (const root of pendingBrandRoots) replaceBrandText(root);" in source

    observer_tail = source.split("observer = new MutationObserver(scheduleDynamicBranding)", 1)[1]
    assert "characterData: true" not in observer_tail
    assert "window.requestAnimationFrame(apply)" not in observer_tail


def test_mobile_runtime_filters_and_coalesces_global_mutation_work() -> None:
    source = _read("roxy-mobile-runtime.js")
    assert "function mutationAffectsNavigation(mutation)" in source
    assert "if (!mutations.some(mutationAffectsNavigation)) return;" in source
    assert "function scheduleBackSync()" in source
    assert "if (state.backFrame) return;" in source
    assert "scheduleBackSync();" in source


def test_telegram_mobile_disables_large_live_backdrop_blurs() -> None:
    css = _read("roxy-mobile-runtime.css")
    for platform in ("ios", "android"):
        assert f'html[data-roxy-platform="{platform}"] .product-header' in css
        assert f'html[data-roxy-platform="{platform}"] .studio-bottom-nav' in css
    assert "-webkit-backdrop-filter: none !important" in css
