from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_dispatcher_exposes_only_mini_app_launcher() -> None:
    dispatcher = _read("app/bot/dispatcher.py")
    assert "from app.bot.handlers import launcher" in dispatcher
    assert "dispatcher.include_router(launcher.router)" in dispatcher
    for retired in (
        "start.router",
        "feed.router",
        "trends.router",
        "prompt_tools.router",
        "admin.router",
        "admin_extensions.router",
        "generation.router",
        "support.router",
    ):
        assert retired not in dispatcher


def test_launcher_removes_legacy_reply_keyboard_and_routes_everything_to_app() -> None:
    launcher = _read("app/bot/handlers/launcher.py")
    keyboards = _read("app/bot/keyboards.py")
    assert "ReplyKeyboardRemove()" in launcher
    assert "app_launcher_menu" in launcher
    assert "@router.message(CommandStart())" in launcher
    assert "@router.message()" in launcher
    assert "Do not expose a parallel text UI" in launcher
    assert "web_app=WebAppInfo" in keyboards
    assert 'text="🚀 Открыть ROXY"' in keyboards
    assert 'query["start_payload"] = start_payload' in keyboards


def test_onboarding_is_owned_by_mini_app_not_text_bot() -> None:
    brand = _read("app/web/mini_app/roxy-brand.js")
    onboarding = _read("app/web/mini_app/roxy-app-onboarding.js")
    css = _read("app/web/mini_app/roxy-app-onboarding.css")
    assert "roxy-app-onboarding.js?v=1" in brand
    assert "roxy-app-onboarding.css?v=1" in brand
    assert 'api("/api/v1/onboarding")' in onboarding
    assert 'api("/api/v1/onboarding/complete"' in onboarding
    assert "innerHTML" not in onboarding
    assert "roxy-app-onboarding-open" in css
