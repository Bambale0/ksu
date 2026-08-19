from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_rx_boot_loader_is_wired_into_mini_app() -> None:
    index = _read("index.html")
    brand = _read("roxy-brand.js")
    assert '/mini-app/boot-loader.css' in index
    assert 'id="rxBootLoader"' in index
    assert '/mini-app/boot-loader.js' in index
    assert index.index('/mini-app/boot-loader.js') > index.index('/mini-app/roxy-brand.js')
    assert '/mini-app/roxy-boot-logo-v5.css' in brand


def test_rx_boot_loader_animation_matches_roxy_brand() -> None:
    css = _read("boot-loader.css")
    override = _read("roxy-boot-logo-v5.css")
    for token in (
        "conic-gradient(",
        "--rx-loader-violet",
        "--rx-loader-pink",
        "rx-loader-spin",
        "rx-loader-core-pulse",
        "rx-loader-progress",
        "@media (prefers-reduced-motion: reduce)",
        "env(safe-area-inset-bottom, 0px)",
    ):
        assert token in css
    assert '/mini-app/assets/roxy-rx-logo-v5.webp?v=5' in override
    assert "background-size: cover !important" in override
    assert ".rx-loader-monogram" in override


def test_rx_boot_loader_has_defensive_exit() -> None:
    script = _read("boot-loader.js")
    assert "MIN_VISIBLE_MS" in script
    assert "HARD_TIMEOUT_MS" in script
    assert 'window.addEventListener("load"' in script
    assert 'loader.classList.add("is-leaving")' in script
    assert "loader.remove()" in script


def test_rx_logo_asset_is_small_enough_for_mobile_boot() -> None:
    asset = MINI / "assets" / "roxy-rx-logo-v5.webp"
    payload = asset.read_bytes()
    assert asset.exists()
    assert 1_000 < len(payload) < 50_000
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"
