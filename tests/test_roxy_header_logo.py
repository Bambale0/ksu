from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_current_rx_asset_is_used_inside_brand_marks() -> None:
    script = _read("roxy-brand.js")
    assert 'const BRAND_LOGO_SRC = "/mini-app/assets/roxy-rx-logo-v5.webp?v=5"' in script
    assert "function ensureBrandLogo" in script
    assert 'ensureBrandLogo(".brand-mark", headerBrand)' in script
    assert 'ensureBrandLogo(".studio-sidebar-mark", sidebar)' in script
    assert 'logo.dataset.roxyBrandLogo = "true"' in script
    assert "mark.replaceChildren(logo)" in script
    assert 'logo.width = 256' in script
    assert 'logo.height = 256' in script
    assert 'setText(".brand-mark", "RX", headerBrand)' not in script


def test_header_logo_polish_loads_after_other_brand_layers() -> None:
    script = _read("roxy-brand.js")
    assert '/mini-app/roxy-header-logo.css?v=5' in script
    assert script.index('/mini-app/roxy-header-logo.css?v=5') > script.index('/mini-app/roxy-iphone-polish.css')
    assert script.index('/mini-app/roxy-header-logo.css?v=5') > script.index('/mini-app/roxy-approved-surfaces.css')


def test_rx_logo_keeps_existing_rounded_arch_without_webview_blending() -> None:
    css = _read("roxy-header-logo.css")
    for token in (
        ".roxy-brand-ready .brand-mark",
        ".roxy-brand-mark-logo",
        "overflow: hidden",
        "border-radius: 10px",
        "object-fit: cover",
        "mix-blend-mode: normal !important",
        "filter: none !important",
        "transform: none !important",
        "@media (max-width: 430px)",
        ".roxy-approved-brand .brand-mark",
    ):
        assert token in css


def test_canonical_rx_asset_is_valid_small_webp() -> None:
    asset = MINI / "assets" / "roxy-rx-logo-v5.webp"
    payload = asset.read_bytes()
    assert 1_000 < len(payload) < 50_000
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"
