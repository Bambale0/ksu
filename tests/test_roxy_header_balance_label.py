from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_header_balance_is_normalized_to_rox() -> None:
    bridge = (MINI / "roxy-notification-badge-bridge.js").read_text(encoding="utf-8")
    assert 'document.getElementById("balanceValue")' in bridge
    assert '" ROX"' in bridge
    assert "attachBalance" in bridge
    assert "balanceObserver" in bridge
