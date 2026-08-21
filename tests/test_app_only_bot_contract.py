from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_dispatcher_exposes_only_operator_admin_and_mini_app_launcher() -> None:
    dispatcher = _read("app/bot/dispatcher.py")
    assert "from app.bot.handlers import admin, admin_extensions, launcher" in dispatcher
    assert "dispatcher.include_router(admin.router)" in dispatcher
    assert "dispatcher.include_router(admin_extensions.router)" in dispatcher
    assert "dispatcher.include_router(launcher.router)" in dispatcher
    assert dispatcher.index("dispatcher.include_router(admin.router)") < dispatcher.index(
        "dispatcher.include_router(launcher.router)"
    )
    assert dispatcher.index("dispatcher.include_router(admin_extensions.router)") < dispatcher.index(
        "dispatcher.include_router(launcher.router)"
    )
    for retired_customer_router in (
        "start.router",
        "feed.router",
        "trends.router",
        "prompt_tools.router",
        "generation.router",
        "support.router",
    ):
        assert retired_customer_router not in dispatcher


def test_launcher_uses_reply_keyboard_and_routes_everything_to_app() -> None:
    launcher = _read("app/bot/handlers/launcher.py")
    keyboards = _read("app/bot/keyboards.py")
    assert "app_launcher_menu" in launcher
    assert "@router.message(CommandStart())" in launcher
    assert "@router.message()" in launcher
    assert "Do not expose a parallel text UI" in launcher
    assert "ReplyKeyboardRemove" not in launcher
    assert "ReplyKeyboardMarkup" in keyboards
    assert "KeyboardButton" in keyboards
    assert "web_app=WebAppInfo" in keyboards
    assert 'OPEN_APP_TEXT = "🚀 Открыть ROXY"' in keyboards
    assert 'QUICK_SUPPORT_TEXT = "🆘 Поддержка"' in keyboards
    assert 'query["start_payload"] = start_payload' in keyboards


def test_onboarding_is_owned_by_next_mini_app_not_text_bot() -> None:
    app = _read("frontend/mini-app/components/roxy-app.tsx")
    api = _read("frontend/mini-app/lib/api.ts")
    assert "<Onboarding" in app
    assert "function Onboarding" in app
    assert "api.onboarding()" in app
    assert "api.completeOnboarding()" in app
    assert 'onboarding: () => request<Record<string, any>>("/api/v1/onboarding")' in api
    assert 'completeOnboarding: () => request<Record<string, any>>("/api/v1/onboarding/complete"' in api
    assert "innerHTML" not in app
    assert "app/web/mini_app" not in app
