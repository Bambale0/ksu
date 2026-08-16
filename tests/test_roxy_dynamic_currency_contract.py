from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def test_dynamic_currency_copy_normalizes_legacy_credit_labels() -> None:
    script = (MINI / "roxy-approved-home.js").read_text(encoding="utf-8")
    assert "normalizeCopyString" in script
    assert "normalizeVisibleCopy(document.body)" in script
    assert "кредит" in script
    assert " ROX" in script