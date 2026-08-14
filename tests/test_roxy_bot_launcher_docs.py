from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_roxy_bot_launcher_docs_match_minimal_webapp_boundary() -> None:
    docs = (ROOT / "docs" / "ROXY_BOT_LAUNCHER.md").read_text(encoding="utf-8")
    for token in (
        "🚀 Открыть ROXY",
        "✨ Создать",
        "▦ Каталог",
        "≡ История",
        "👤 Профиль",
        "web_app",
        "PUBLIC_BASE_URL",
        "callback",
        "Mini App",
    ):
        assert token in docs
