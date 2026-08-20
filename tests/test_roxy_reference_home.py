from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_legacy_reference_home_layers_are_retired() -> None:
    for name in ("roxy-reference-home.js", "roxy-reference-home.css", "roxy-reference-order.css"):
        assert not (MINI / name).exists()


def test_notification_bridge_only_bridges_notifications_and_balance() -> None:
    bridge = _read("roxy-notification-badge-bridge.js")
    assert "mountReferenceHomeLayer" not in bridge
    assert "roxy-reference-home" not in bridge
    assert "roxy-reference-order" not in bridge
    assert 'document.getElementById("profileUnreadBadge")' in bridge
    assert 'current.replace(/\\s*кр\\.?$/iu, " ROX")' in bridge


def test_concept_one_home_owns_start_hierarchy() -> None:
    approved_home = _read("roxy-approved-home.js")
    design = _read("roxy-design-system.css")
    assert "Создавай. Публикуй." in approved_home
    assert "Зарабатывай." in approved_home
    assert 'button("✦ Создать"' in approved_home
    assert 'button("Каталог"' in approved_home
    assert ".roxy-approved-hero" in design
    assert ".studio-home-actions" in design
    assert ".roxy-media-grid" in design
