from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_roxy_bot_main_menu_uses_minimal_welcome_copy() -> None:
    start = (ROOT / "app" / "bot" / "handlers" / "start.py").read_text(encoding="utf-8")
    block = start.split("async def _send_main_menu", 1)[1].split(
        "async def _profile_text", 1
    )[0]

    assert "<b>ROXY ✨</b>" in block
    assert "<b>Создавай. Вдохновляй.</b>" in block
    assert "👇<b>Нажми, чтобы открыть ROXY</b>" in block
    assert 'parse_mode="HTML"' in block

    for legacy_copy in (
        "Привет,",
        "Баланс ROX",
        "Заработок партнёра",
        "1 ROX = 1 ₽",
        "Выбери действие:",
    ):
        assert legacy_copy not in block
