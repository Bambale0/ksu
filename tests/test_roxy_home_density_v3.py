from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_home_density_is_part_of_the_canonical_design_system() -> None:
    source = _read("roxy-brand.js")
    css = _read("roxy-design-system.css")
    assert '/mini-app/roxy-design-system.css?v=1' in source
    assert '/mini-app/roxy-fhd-density.css' not in source
    assert '/mini-app/roxy-home-density-v3.css' not in source
    assert ".studio-home-actions" in css
    assert ".roxy-media-grid" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "@media (min-width: 720px)" in css
    assert "@media (max-width: 430px)" in css


def test_duplicate_home_cta_and_balance_are_removed_without_hiding_concept_hero() -> None:
    source = _read("roxy-brand.js")
    assert 'document.getElementById("roxyHomeBalance")?.remove()' in source
    assert 'document.getElementById("roxyCreateCta")?.remove()' in source
    assert 'card.id = "roxyHomeBalance"' not in source
    assert "hero.hidden = true" not in source


def test_partner_promo_follows_the_primary_hero() -> None:
    source = _read("roxy-brand.js")
    assert 'const promo = document.getElementById("roxyPromoSection")' in source
    assert 'const hero = document.getElementById("roxyApprovedHero")' in source
    assert 'hero.insertAdjacentElement("afterend", promo)' in source
    assert "home.prepend(promo)" not in source


def test_home_cards_remain_compact_touch_friendly_and_mobile_first() -> None:
    css = _read("roxy-design-system.css")
    for token in (
        ".studio-home-action",
        ".roxy-media-card",
        "min-height: 102px",
        "min-height: 44px",
        "--roxy-control-h: 46px",
        "grid-template-columns: repeat(2, minmax(0, 1fr))",
    ):
        assert token in css
