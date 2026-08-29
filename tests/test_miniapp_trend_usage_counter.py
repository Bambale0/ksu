from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI_APP = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_trend_usage_count_remains_in_public_api_contract() -> None:
    service = _read(ROOT / "app" / "services" / "trends.py")
    types = _read(MINI_APP / "lib" / "types.ts")

    assert '"usage_count": recipe["usage_count"]' in service
    assert "usage_count?: number" in types


def test_trend_usage_count_is_visible_on_catalog_card_and_detail() -> None:
    rail = _read(MINI_APP / "components" / "live-trend-rail.tsx")
    detail = _read(MINI_APP / "app" / "trend" / "page.tsx")

    for source in (rail, detail):
        assert "trendUsageLabel(trend.usage_count)" in source
        assert "запуск" in source
