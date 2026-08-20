from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_home_uses_concept_one_hero_without_legacy_density_layer() -> None:
    brand = _read("roxy-brand.js")
    css = _read("roxy-design-system.css")
    assert not (MINI / "roxy-fhd-density.css").exists()
    assert 'document.getElementById("roxyHomeBalance")?.remove()' in brand
    assert 'document.getElementById("roxyCreateCta")?.remove()' in brand
    assert "hero.hidden = true" not in brand
    assert ".roxy-approved-hero" in css
    assert "min-height: 178px" in css


def test_wide_layout_is_owned_by_canonical_design_system() -> None:
    css = _read("roxy-design-system.css")
    for token in (
        "--roxy-content: 840px",
        "@media (min-width: 720px)",
        "grid-template-columns: minmax(0, 1.03fr) minmax(300px, .97fr)",
        ".family-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }",
    ):
        assert token in css


def test_backend_tools_remain_available_without_owning_primary_navigation() -> None:
    source = _read("roxy-parity-navigation.js")
    navigation = _read("roxy-customer-navigation.js")
    for token in (
        'section.id = "roxyHomeTools"',
        'homeTool("catalog", "Каталог", openCatalog)',
        'homeTool("trend", "Тренды"',
        'homeTool("prompt", "Prompt"',
        'homeTool("batch", "Batch"',
        'homeTool("image", "Референсы"',
        'homeTool("bell", "События"',
        'homeTool("support", "Поддержка"',
        'window.RoxyIcons?.create?.(name, { size: 22 })',
    ):
        assert token in source
    assert 'catalog: "Каталог"' in navigation
    assert 'PRIMARY_ROUTES = ["home", "catalog", "create", "history", "profile"]' in navigation


def test_home_tool_grid_remains_compact_on_telegram_mobile() -> None:
    css = _read("roxy-parity-navigation.css")
    for token in (
        ".roxy-home-tools-grid",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        "min-height: 54px",
        ".roxy-home-tool-glyph",
    ):
        assert token in css
