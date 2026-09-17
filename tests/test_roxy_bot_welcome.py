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
    assert "PartnerPromoProgramService.get_config(session)" in block
    assert "promo_program.welcome_rox" in block
    assert "promo_program.topup_partner_rox" in block
    assert 'f"🎁 +{welcome_rox} ROX — сразу после регистрации\\n"' in block
    assert 'f"💎 +{topup_partner_rox} ROX — после успешного пополнения реферала\\n\\n"' in block

    # The launcher intentionally exposes only the two approved ROX facts.
    for forbidden_money_copy in (
        "Бонусы по промокоду",
        "после активации промокода",
        "promo_program.first_line_percent",
        "Партнёру:",
        "%",
        "За обычное приглашение",
        "topup_user_rox",
        "topup_user_min_rub",
    ):
        assert forbidden_money_copy not in block

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
