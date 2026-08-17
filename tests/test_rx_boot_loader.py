from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_rx_boot_loader_is_wired_into_mini_app() -> None:
    index = _read("index.html")
    assert '/mini-app/boot-loader.css' in index
    assert 'id="rxBootLoader"' in index
    assert '/mini-app/assets/roxy-rx-logo.webp' in index
    assert '/mini-app/boot-loader.js' in index
    assert index.index('/mini-app/boot-loader.js') > index.index('/mini-app/roxy-brand.js')


def test_rx_boot_loader_animation_matches_roxy_brand() -> None:
    css = _read("boot-loader.css")
    for token in (
        "conic-gradient(",
        "--rx-loader-violet",
        "--rx-loader-pink",
        "rx-loader-spin",
        "rx-loader-core-pulse",
        "rx-loader-scan",
        "rx-loader-progress",
        "@media (prefers-reduced-motion: reduce)",
        "env(safe-area-inset-bottom, 0px)",
    ):
        assert token in css


def test_rx_boot_loader_has_defensive_exit() -> None:
    script = _read("boot-loader.js")
    assert "MIN_VISIBLE_MS" in script
    assert "HARD_TIMEOUT_MS" in script
    assert 'window.addEventListener("load"' in script
    assert 'loader.classList.add("is-leaving")' in script
    assert "loader.remove()" in script


def test_rx_logo_asset_is_small_enough_for_mobile_boot() -> None:
    asset = MINI / "assets" / "roxy-rx-logo.webp"
    assert asset.exists()
    assert asset.stat().st_size < 50_000
