from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_reference_home_has_clear_start_hierarchy_and_trend_preview() -> None:
    script = _read("roxy-reference-home.js")
    css = _read("roxy-reference-home.css")

    for label in ("С чего начать", "По шаблону", "С нуля", "Тренды", "Шаблоны", "Инструменты"):
        assert label in script
    for tool in ("Prompt", "Batch", "Референсы", "Поддержка"):
        assert tool in script
    assert 'fetch("/api/v1/trends?limit=100"' in script
    assert "/mini-app/trends.html?trend=" in script
    assert "grid-template-columns: repeat(2" in css
    assert "aspect-ratio: 4 / 5" in css
    assert "opacity: .09" in css  # restrained texture, far below the 30% ceiling
    assert "#createHome > .hero-card" in css


def test_reference_home_layer_is_mounted_by_existing_product_runtime() -> None:
    bridge = _read("roxy-notification-badge-bridge.js")
    assert "/mini-app/roxy-reference-home.css" in bridge
    assert "/mini-app/roxy-reference-home.js" in bridge
    assert "mountReferenceHomeLayer();" in bridge
