from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_compact_home_density_layer_is_mounted_after_fhd_layer() -> None:
    source = _read("roxy-brand.js")
    fhd = 'mountLayer({ css: "/mini-app/roxy-fhd-density.css" });'
    compact = 'mountLayer({ css: "/mini-app/roxy-home-density-v3.css" });'
    mobile = 'mountLayer({ css: "/mini-app/roxy-mobile-runtime.css", js: "/mini-app/roxy-mobile-runtime.js" });'
    assert fhd in source
    assert compact in source
    assert mobile in source
    assert source.index(fhd) < source.index(compact) < source.index(mobile)


def test_create_cta_lives_inside_hero_and_duplicate_balance_is_removed() -> None:
    source = _read("roxy-brand.js")
    assert 'document.getElementById("roxyHomeBalance")?.remove()' in source
    assert 'if (cta.parentElement !== copy) copy.appendChild(cta)' in source
    assert 'card.id = "roxyHomeBalance"' not in source


def test_promos_are_moved_below_model_directions() -> None:
    source = _read("roxy-brand.js")
    assert 'const promo = document.getElementById("roxyPromoSection")' in source
    assert 'families.insertAdjacentElement("afterend", promo)' in source


def test_promos_cannot_become_billboard_cards() -> None:
    css = _read("roxy-home-density-v3.css")
    for token in (
        "min-height: 108px !important",
        "max-height: 108px",
        "font-size: 17px",
        "-webkit-line-clamp: 2",
        "grid-auto-columns: minmax(300px, 42%)",
        "min-height: 92px !important",
        "grid-auto-columns: 82%",
    ):
        assert token in css


def test_first_screen_tool_grid_remains_four_columns_on_mobile() -> None:
    css = _read("roxy-home-density-v3.css")
    assert ".roxy-home-tools-grid" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    assert "min-height: 52px" in css
