from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_final_surface_layer_is_last_roxy_brand_css_layer() -> None:
    brand = (MINI / "roxy-brand.js").read_text(encoding="utf-8")
    approved = brand.index('/mini-app/roxy-approved-theme.css')
    final = brand.index('/mini-app/roxy-approved-surfaces.css')
    assert final > approved


def test_final_surface_layer_uses_approved_logo_asset() -> None:
    css = (MINI / "roxy-approved-surfaces.css").read_text(encoding="utf-8")
    assert "url('/mini-app/roxy-logo.svg')" in css
    assert ".brand-mark" in css
    assert ".studio-sidebar-mark" in css
