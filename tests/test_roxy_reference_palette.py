from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_reference_home_uses_roxy_violet_pink_palette() -> None:
    css = (MINI / "roxy-reference-home.css").read_text(encoding="utf-8").lower()
    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e", "rgba(244,197,122"):
        assert legacy_gold not in css
    assert "#8f63ff" in css
    assert "#ff69c9" in css
    assert "#b184ff" in css
