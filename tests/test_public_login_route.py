import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

main = importlib.import_module("app.main")
ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.asyncio
async def test_login_is_separate_noncacheable_auth_screen():
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        login = await client.get("/login", follow_redirects=False)
        root = await client.get("/", follow_redirects=False)
    assert login.status_code == 200
    assert "no-store" in login.headers["cache-control"]
    assert "Войти в ROXY" in login.text
    assert "hero-art" not in login.text
    assert 'href="/login" data-app-link' in root.text
    assert 'href="/mini-app/" data-app-link' not in root.text

def test_browser_gate_redirects_to_login_without_removing_native_auth():
    source = (ROOT / "frontend/mini-app/components/telegram-auth-boundary.tsx").read_text()
    assert 'if (nativeInitData)' in source
    assert "installBrowserInitDataFacade" in source
    assert 'window.location.replace(loginUrl)' in source
    assert "<TelegramBrowserLogin" not in source
