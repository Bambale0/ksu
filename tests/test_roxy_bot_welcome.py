from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_roxy_bot_launcher_uses_friendly_welcome_copy() -> None:
    launcher = (ROOT / "app" / "bot" / "handlers" / "launcher.py").read_text(encoding="utf-8")
    block = launcher.split("async def _send_launcher", 1)[1].split(
        "@router.callback_query", 1
    )[0]

    assert "<b>Привет! Это ROXY — твоя AI-студия.</b>" in block
    assert "Создавай фото, видео и музыку" in block
    assert "публикуй в ленту" in block
    assert "партнёрский кабинет" in block
    assert "app_launcher_menu" in block
    assert 'parse_mode="HTML"' in block

    for legacy_or_internal_copy in (
        "ROXY теперь работает через приложение",
        "Все функции — генерации, баланс, история, профиль и поддержка — внутри Mini App",
        "KIE",
        "provider",
        "media routes",
        "1 ROX = 1 ₽",
        "Выбери действие:",
    ):
        assert legacy_or_internal_copy not in block
