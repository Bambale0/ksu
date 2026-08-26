from pathlib import Path


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_frontend_preserves_startapp_and_init_data_before_telegram_sdk() -> None:
    layout = _source("frontend/mini-app/app/layout.tsx")
    telegram = _source("frontend/mini-app/lib/telegram.ts")

    assert 'id="roxy-launch-snapshot"' in layout
    assert layout.index('id="roxy-launch-snapshot"') < layout.index("telegram-web-app.js")
    assert "__ROXY_INITIAL_LAUNCH__" in telegram
    assert "tgWebAppStartParam" in telegram
    assert "tgWebAppData" in telegram
    assert "getInitDataFallback" in telegram
    assert "initDataUnsafe?.start_param" in telegram
    assert 'headers["X-Telegram-Init-Data"]' in telegram
    assert 'headers["X-Telegram-Start-Param"]' in telegram


def test_product_owned_start_payload_precedes_generic_startapp_fallback() -> None:
    telegram = _source("frontend/mini-app/lib/telegram.ts")

    assert 'const URL_START_PARAM_NAMES = ["tgWebAppStartParam", "start_payload", "startapp"]' in telegram


def test_backend_applies_recovered_referral_before_user_creation() -> None:
    deps = _source("app/api/deps.py")

    assert "x_telegram_start_param" in deps
    assert "resolved_start_param = signed_start_param or fallback_start_param or None" in deps
    assert "_validated_startapp_inviter(session, resolved_start_param)" in deps
    assert deps.index("_validated_startapp_inviter(session, resolved_start_param)") < deps.index(
        "UserService.get_or_create"
    )


def test_backend_prefers_signed_start_param_over_recovered_header() -> None:
    deps = _source("app/api/deps.py")

    assert "signed_start_param =" in deps
    assert "fallback_start_param =" in deps
    assert "resolved_start_param = signed_start_param or fallback_start_param or None" in deps


def test_all_frontend_api_clients_use_shared_telegram_headers() -> None:
    api = _source("frontend/mini-app/lib/api.ts")
    customer_api = _source("frontend/mini-app/lib/customer-api.ts")

    assert 'import { telegramHeaders } from "./telegram"' in api
    assert '...telegramHeaders(Boolean(init.body) && !isForm)' in api
    assert 'import { telegramHeaders } from "./telegram"' in customer_api
    assert '...telegramHeaders(Boolean(init.body) && !isForm)' in customer_api


def test_runtime_bot_identity_is_not_trusted_to_static_env_only() -> None:
    main = _source("app/main.py")

    assert "bot_info = await bot.get_me()" in main
    assert "settings.bot_username = bot_info.username" in main
    assert "has_main_web_app" in main
