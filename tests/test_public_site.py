"""Marketing domain root is a standalone static site, independent from Mini App."""
import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

main = importlib.import_module("app.main")
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_origin_root_is_standalone_marketing_html_not_redirect() -> None:
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        html = await client.get("/", follow_redirects=False)
        head = await client.head("/", follow_redirects=False)
    assert html.status_code == 200
    assert "text/html" in html.headers["content-type"]
    assert "ROXY — создавай фото и видео" in html.text
    assert 'class="hero-mosaic"' in html.text
    assert "/site-assets/styles.css" in html.text
    assert "/mini-app/_next/" not in html.text
    assert "no-store" in html.headers["cache-control"]
    assert head.status_code == 200
    assert not head.content


@pytest.mark.asyncio
async def test_public_assets_served_from_independent_site_directory() -> None:
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        css = await client.get("/site-assets/styles.css")
        low = await client.get("/site-assets/atlas-1920.webp")
        high = await client.get("/site-assets/atlas-3840.webp")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert 'url("/site-assets/atlas-1920.webp")' in css.text
    for asset in (low, high):
        assert asset.status_code == 200
        assert "image/webp" in asset.headers["content-type"]
        assert asset.content[:4] == b"RIFF"
        assert asset.content[8:12] == b"WEBP"
        assert len(asset.content) > 100_000


@pytest.mark.asyncio
async def test_removed_landing_url_is_unavailable_and_mini_app_mount_is_unchanged() -> None:
    routes = {getattr(route, "path", None): route for route in main.app.routes}
    assert "/landing" not in routes
    assert "/mini-app" in routes
    assert Path(routes["/mini-app"].app.directory) == main.mini_app_dir
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        for url in ("/landing", "/landing/", "/landing/index.html", "/landing/styles.css"):
            resp = await client.get(url, follow_redirects=False)
            assert resp.status_code == 404, url
