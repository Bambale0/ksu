from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_customer_surfaces_resolve_to_concept_one_palette() -> None:
    css = (MINI / "roxy-design-system.css").read_text(encoding="utf-8").lower()
    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e", "rgba(244,197,122"):
        assert legacy_gold not in css
    for token in ("#0b0b10", "#9b5cff", "#ff5fb7", "#ffffff", "#a6a6b3"):
        assert token in css


def test_reference_feature_uses_shared_roxy_tokens_for_primary_accents() -> None:
    css = (MINI / "roxy-reference-home.css").read_text(encoding="utf-8")
    assert "var(--roxy-violet" in css
    assert "var(--roxy-pink" in css
    assert "var(--roxy-text" in css
