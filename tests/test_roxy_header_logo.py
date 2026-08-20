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


def test_brand_marks_are_owned_by_canonical_design_system() -> None:
    script = _read("roxy-brand.js")
    css = _read("roxy-design-system.css")
    assert '/mini-app/roxy-design-system.css?v=1' in script
    assert '/mini-app/roxy-header-logo.css' not in script
    for token in (
        ".brand-mark",
        ".studio-sidebar-mark",
        ".roxy-brand-mark-logo",
        "overflow: hidden",
        "object-fit: contain",
        "@media (max-width: 430px)",
    ):
        assert token in css


def test_canonical_rx_asset_is_valid_small_webp() -> None:
    asset = MINI / "assets" / "roxy-rx-logo-v5.webp"
    payload = asset.read_bytes()
    assert 1_000 < len(payload) < 50_000
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"
