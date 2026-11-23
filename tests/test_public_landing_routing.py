"""Regression: origin root is marketing and /mini-app/ is the only app entry."""
from pathlib import Path
import importlib

import pytest
from httpx import ASGITransport, AsyncClient

main_module = importlib.import_module("app.main")


@pytest.mark.asyncio
async def test_root_serves_exported_next_html_without_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<!doctype html><html><body>ROXY-NEXT-ENTRY</body></html>"
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    monkeypatch.setattr(main_module, "mini_app_dir", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)
        head = await client.head("/", follow_redirects=False)

    assert response.status_code == 200
    assert "ROXY-NEXT-ENTRY" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"].startswith("no-store")
    assert head.status_code == 200
    assert head.content == b""


@pytest.mark.asyncio
async def test_obsolete_landing_path_is_gone() -> None:
    async with AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test") as client:
        for path in ("/landing", "/landing/", "/landing/index.html", "/landing/styles.css"):
            response = await client.get(path, follow_redirects=False)
            assert response.status_code == 404, (path, response.status_code)
