from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_main_mini_app_uses_roxy_brand_from_first_paint() -> None:
    html = _read("index.html")
    assert "<title>ROXY · AI Creative Studio</title>" in html
    assert 'content="#09080f"' in html
    assert '/mini-app/roxy-brand.css' in html
    assert '/mini-app/roxy-brand.js' in html
    assert "ROXY · AI CREATIVE STUDIO" in html
    assert "Привет! Это ROXY ✨" in html
    assert "Твори. Генерируй. Зарабатывай." in html
    assert "Внутренние кредиты ROXY" in html
    assert "Ксю" not in html
    assert "КСЮ" not in html


def test_all_standalone_studio_surfaces_share_roxy_brand_layer() -> None:
    for name in ("trends.html", "prompt-tools.html", "batch.html"):
        html = _read(name)
        assert "ROXY" in html
        assert '/mini-app/roxy-brand.css' in html
        assert '/mini-app/roxy-brand.js' in html
        assert 'content="#09080f"' in html
        assert "Ксю" not in html
        assert "КСЮ" not in html


def test_roxy_palette_matches_reference_direction() -> None:
    css = _read("roxy-brand.css")
    for token in (
        "--roxy-bg: #09080f",
        "--roxy-surface: #18171f",
        "--roxy-violet: #8f6bff",
        "--roxy-purple: #b86cff",
        "--roxy-pink: #ff73ca",
        "--roxy-gradient:",
        "radial-gradient",
        "roxy-create-cta",
        "studio-bottom-nav",
        "studio-sidebar",
    ):
        assert token in css


def test_roxy_brand_runtime_keeps_telegram_chrome_and_dynamic_copy_aligned() -> None:
    script = _read("roxy-brand.js")
    for token in (
        'setHeaderColor?.("#09080f")',
        'setBackgroundColor?.("#09080f")',
        'setBottomBarColor?.("#09080f")',
        "MutationObserver",
        "ROXY · AI CREATIVE STUDIO",
        "roxyHomeBalance",
        "roxyCreateCta",
    ):
        assert token in script
    assert "initDataUnsafe" not in script


def test_roxy_visual_rebrand_does_not_hardcode_reference_economics() -> None:
    combined = "\n".join(
        _read(name)
        for name in (
            "index.html",
            "roxy-brand.js",
            "roxy-brand.css",
            "trends.html",
            "prompt-tools.html",
            "batch.html",
        )
    )
    assert "1 ROX = 1" not in combined
    assert "1 ROX = 10" not in combined
    assert "ROX =" not in combined


def test_shell_integration_mounts_brand_after_product_layers() -> None:
    bridge = _read("shell-integration.js")
    assert "function mountRoxyBrand()" in bridge
    assert '/mini-app/roxy-brand.css' in bridge
    assert '/mini-app/roxy-brand.js' in bridge
    assert bridge.index("mountStudioWorkspace();") < bridge.index("mountRoxyBrand();")
