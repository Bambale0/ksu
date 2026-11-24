"""Regression: web-only ROXY logout must revoke the server session.

Never expose this action in the native Telegram WebView, and never navigate
as if logout succeeded when the backend returned an error.
"""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.services.web_sessions import (
    COOKIE, current_web_user_id, issue_web_session, revoke_web_session,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, **kwargs: object) -> bool:
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def request_for(redis: FakeRedis, *, cookie: str = "") -> Request:
    headers = [(b"host", b"roxy.test")]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/web-auth/logout",
        "scheme": "https", "headers": headers,
        "server": ("roxy.test", 443), "client": ("127.0.0.1", 9000),
        "app": SimpleNamespace(state=SimpleNamespace(redis=redis)),
    })


@pytest.mark.asyncio
async def test_web_profile_logout_revokes_opaque_session_before_redirect() -> None:
    redis = FakeRedis()
    user_id = uuid4()
    issued = Response()
    await issue_web_session(request_for(redis), issued, user_id)
    set_cookie = issued.headers["set-cookie"]
    assert COOKIE in set_cookie
    assert "httponly" in set_cookie.lower()
    token = set_cookie.split(";", 1)[0]
    request = request_for(redis, cookie=token)
    assert await current_web_user_id(request) == user_id

    logout_response = Response()
    await revoke_web_session(request, logout_response)

    assert await current_web_user_id(request) is None
    assert "max-age=0" in logout_response.headers["set-cookie"].lower()


def test_web_logout_is_rendered_only_for_browser_session_in_all_profile_surfaces() -> None:
    source = (ROOT / "frontend/mini-app/components/web-profile-logout.tsx").read_text(encoding="utf-8")
    assert "isWebSessionAuthenticated()" in source
    assert "getInitDataFallback()" in source
    assert 'fetch("/api/v1/web-auth/logout"' in source
    assert 'method: "POST"' in source
    assert 'credentials: "same-origin"' in source
    assert "if (!response.ok)" in source
    assert "clearBrowserInitData();" in source
    assert 'window.location.replace("/login")' in source
    assert "role=\"alert\"" in source

    for path in (
        "frontend/mini-app/components/roxy-social-app.tsx",
        "frontend/mini-app/components/roxy-app.tsx",
        "frontend/mini-app/app/account/page.tsx",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "<WebProfileLogout />" in text

@pytest.mark.asyncio
async def test_invalid_cookie_cannot_break_new_login_or_logout() -> None:
    redis = FakeRedis()
    request = request_for(redis, cookie=COOKIE + "=" + "!" * 64)
    assert await current_web_user_id(request) is None
    await revoke_web_session(request, Response())
    issued = Response()
    owner = uuid4()
    await issue_web_session(request, issued, owner)
    assert await current_web_user_id(request_for(redis, cookie=issued.headers["set-cookie"].split(";")[0])) == owner


@pytest.mark.parametrize(("raw", "expected"), [
    ("/mini-app/?route=create&create_media=video&ref=QA", "/mini-app/?route=create&create_media=video&ref=QA"),
    ("/mini-app/trend/?id=11111111-1111-4111-8111-111111111111&ref=QA", "/mini-app/trend/?id=11111111-1111-4111-8111-111111111111&ref=QA"),
    ("/mini-app/?route=partners&ref=QA&unknown=discard", "/mini-app/?route=partners&ref=QA"),
    ("https://example.invalid", "/mini-app/"),
    ("//example.invalid/mini-app/", "/mini-app/"),
    ("/mini-app/trend/?id=invalid", "/mini-app/"),
])
def test_provider_callback_uses_only_verified_studio_destinations(raw, expected):
    from app.api.v1.web_auth import _target_path

    assert _target_path(raw) == expected
