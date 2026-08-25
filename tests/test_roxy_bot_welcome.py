from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_roxy_bot_launcher_uses_welcoming_copy_and_support() -> None:
    launcher = (ROOT / "app" / "bot" / "handlers" / "launcher.py").read_text(encoding="utf-8")
    block = launcher.split("async def _send_launcher", 1)[1].split(
        "@router.callback_query", 1
    )[0]

    assert "<b>Добро пожаловать в ROXY ✨</b>" in block
    assert "Создавайте изображения, видео и музыку" in block
    assert "🚀 Открыть ROXY" in block
    assert "_support_line()" in block
    assert "Поддержка:" in launcher
    assert 'parse_mode="HTML"' in block

    for legacy_copy in (
        "ROXY теперь работает через приложение",
        "Все функции — генерации",
        "Быстрый доступ ROXY",
        "Выбери действие:",
    ):
        assert legacy_copy not in block


def test_support_contact_has_safe_fallback_when_not_configured() -> None:
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    launcher = (ROOT / "app" / "bot" / "handlers" / "launcher.py").read_text(encoding="utf-8")

    assert 'support_telegram_url: str = ""' in config
    assert "direct_support_handle(settings.support_telegram_url)" in launcher
    assert "Поддержка: кнопка снизу или раздел «Профиль → Поддержка» в ROXY" in launcher
