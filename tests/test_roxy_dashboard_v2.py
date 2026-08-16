from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_home_no_longer_uses_duplicated_balance_billboard() -> None:
    css = _read("roxy-fhd-density.css")
    assert ".roxy-brand-ready #roxyHomeBalance" in css
    assert "display: none !important" in css
    assert ".roxy-brand-ready #createHome > .hero-card" in css
    assert "min-height: 96px" in css
    assert "font-size: 22px" in css


def test_fhd_home_uses_parallel_workspace_layout() -> None:
    css = _read("roxy-fhd-density.css")
    for token in (
        "--roxy-fhd-max: 1880px",
        "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr)",
        '.home-section[aria-labelledby="familiesHeading"]',
        "grid-template-columns: repeat(6, minmax(0, 1fr))",
    ):
        assert token in css


def test_backend_tools_are_visible_on_home_not_profile_only() -> None:
    source = _read("roxy-parity-navigation.js")
    for token in (
        'section.id = "roxyHomeTools"',
        'homeTool("catalog", "Каталог", openCatalog)',
        'homeTool("feed", "Лента", openFeed)',
        'homeTool("trend", "Тренды"',
        'homeTool("prompt", "Prompt"',
        'homeTool("batch", "Batch"',
        'homeTool("image", "Референсы"',
        'homeTool("bell", "События"',
        'homeTool("support", "Поддержка"',
        'window.RoxyIcons?.create?.(name, { size: 22 })',
        'families.insertAdjacentElement("beforebegin", section)',
    ):
        assert token in source


def test_home_tool_grid_is_compact_on_telegram_mobile() -> None:
    css = _read("roxy-parity-navigation.css")
    for token in (
        ".roxy-home-tools-grid",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        "min-height: 54px",
        ".roxy-home-tool-glyph",
    ):
        assert token in css
