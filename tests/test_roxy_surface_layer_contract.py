from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_canonical_design_system_is_last_roxy_brand_css_layer() -> None:
    brand = (MINI / "roxy-brand.js").read_text(encoding="utf-8")
    canonical = '/mini-app/roxy-design-system.css?v=1'
    assert canonical in brand
    assert brand.rindex(canonical) > brand.index('/mini-app/roxy-app-onboarding.css?v=1')
    assert brand.rindex(canonical) > brand.index('/mini-app/roxy-partner-promo.css?v=12')


def test_canonical_surface_layer_owns_brand_marks_and_product_surfaces() -> None:
    css = (MINI / "roxy-design-system.css").read_text(encoding="utf-8")
    for selector in (
        ".brand-mark",
        ".studio-sidebar-mark",
        ".card",
        ".shell-panel",
        ".roxy-media-card",
        ".studio-result-pane",
        ".feed-card",
        ".payment-package",
        ".studio-bottom-nav",
    ):
        assert selector in css
