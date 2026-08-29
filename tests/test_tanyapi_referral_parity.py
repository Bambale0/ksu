from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request

from app.api import deps
from app.core.config import settings


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/me",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("test", 443),
            "client": ("127.0.0.1", 1),
        }
    )


def _parsed_init_data(start_param: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        start_param=start_param,
        user=SimpleNamespace(
            id=9001,
            first_name="Referral QA",
            last_name=None,
            username="referral_qa",
            language_code="ru",
        ),
    )


def test_frontend_preserves_startapp_and_init_data_before_telegram_sdk() -> None:
    layout = _source("frontend/mini-app/app/layout.tsx")
    telegram = _source("frontend/mini-app/lib/telegram.ts")

    assert 'id="roxy-launch-snapshot"' in layout
    assert layout.index('id="roxy-launch-snapshot"') < layout.index("telegram-web-app.js")
    assert "__ROXY_INITIAL_LAUNCH__" in telegram
    assert "tgWebAppStartParam" in telegram
    assert "tgWebAppData" in telegram
    assert "getInitDataFallback" in telegram
    assert "recoveredInitData = getInitDataFallback()" in telegram
    assert "tg.initData = recoveredInitData" in telegram
    assert "initDataUnsafe?.start_param" in telegram
    assert 'headers["X-Telegram-Init-Data"]' in telegram
    assert 'headers["X-Telegram-Start-Param"]' in telegram
    assert "__roxy_tg_init_data" not in telegram


def test_launch_snapshot_never_persists_telegram_auth_init_data() -> None:
    layout = _source("frontend/mini-app/app/layout.tsx")

    assert "const routingOnly" in layout
    assert 'setItem("__roxy_initial_hash", routingOnly(snapshot.hash))' in layout
    assert 'setItem("__roxy_initial_search", routingOnly(snapshot.search))' in layout
    assert 'setItem("__roxy_initial_hash", snapshot.hash)' not in layout
    assert 'setItem("__roxy_initial_search", snapshot.search)' not in layout
    assert '"tgWebAppData"' not in layout


def test_product_owned_start_payload_precedes_generic_startapp_fallback() -> None:
    telegram = _source("frontend/mini-app/lib/telegram.ts")

    assert 'const URL_START_PARAM_NAMES = ["tgWebAppStartParam", "start_payload", "startapp"]' in telegram


def test_backend_referral_attribution_requires_telegram_signed_start_param() -> None:
    source = _source("app/api/deps.py")

    assert "x_telegram_start_param" in source
    assert "signed_start_param =" in source
    assert "resolved_start_param = signed_start_param or None" in source
    assert "fallback_start_param" not in source
    assert "_validated_startapp_inviter(session, resolved_start_param)" in source
    assert source.index("_validated_startapp_inviter(session, resolved_start_param)") < source.index(
        "UserService.get_or_create"
    )


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


@pytest.mark.asyncio
async def test_authenticated_unsigned_referral_header_cannot_assign_inviter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(deps, "safe_parse_webapp_init_data", lambda _token, _raw: _parsed_init_data(None))
    validate = AsyncMock(return_value=None)
    monkeypatch.setattr(deps, "_validated_startapp_inviter", validate)
    created = SimpleNamespace(id="user-1", is_active=True)
    get_or_create = AsyncMock(return_value=created)
    monkeypatch.setattr(deps.UserService, "get_or_create", get_or_create)
    session = SimpleNamespace(commit=AsyncMock(), info={})

    result = await deps.get_current_user(
        _request(),
        session,  # type: ignore[arg-type]
        "signed-init-data",
        "ref_777",
    )

    assert result is created
    validate.assert_awaited_once_with(session, None)
    assert get_or_create.await_args.kwargs["inviter_telegram_id"] is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_signed_start_param_is_authoritative_over_recovered_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(
        deps,
        "safe_parse_webapp_init_data",
        lambda _token, _raw: _parsed_init_data("ref_111"),
    )
    validate = AsyncMock(return_value=111)
    monkeypatch.setattr(deps, "_validated_startapp_inviter", validate)
    monkeypatch.setattr(
        deps.UserService,
        "get_or_create",
        AsyncMock(return_value=SimpleNamespace(id="user-2", is_active=True)),
    )
    session = SimpleNamespace(commit=AsyncMock(), info={})

    await deps.get_current_user(
        _request(),
        session,  # type: ignore[arg-type]
        "signed-init-data",
        "ref_222",
    )

    validate.assert_awaited_once_with(session, "ref_111")


@pytest.mark.asyncio
async def test_recovered_referral_header_cannot_bypass_invalid_init_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bot_token", "test-token")

    def invalid_init_data(_token: str, _raw: str) -> None:
        raise ValueError("bad signature")

    monkeypatch.setattr(deps, "safe_parse_webapp_init_data", invalid_init_data)
    validate = AsyncMock(return_value=777)
    monkeypatch.setattr(deps, "_validated_startapp_inviter", validate)
    session = SimpleNamespace(commit=AsyncMock(), info={})

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(
            _request(),
            session,  # type: ignore[arg-type]
            "tampered-init-data",
            "ref_777",
        )

    assert exc_info.value.status_code == 401
    validate.assert_not_awaited()
