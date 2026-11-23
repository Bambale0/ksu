from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_root_is_public_marketing_landing_not_a_mini_app_redirect() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://ksuapi.example") as client:
        response = await client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "location" not in response.headers
    assert '<main class="roxy-browser-landing"' in response.text
    assert 'id="features"' in response.text
    assert 'id="how"' in response.text
    assert 'id="examples"' in response.text
    assert 'href="/mini-app/"' in response.text


@pytest.mark.asyncio
async def test_legacy_landing_uses_same_marketing_content_and_asset() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://ksuapi.example") as client:
        root = await client.get("/")
        legacy = await client.get("/landing/")
        css = await client.get("/landing/styles.css")
        atlas = await client.get("/landing/roxy-mosaic.webp")
    assert root.status_code == 200
    assert legacy.status_code == 200
    assert root.text == legacy.text
    assert 'http-equiv="refresh"' not in legacy.text
    assert css.status_code == 200
    assert ".roxy-film-mosaic" in css.text
    assert atlas.status_code == 200
    assert atlas.content[:4] == b"RIFF"
    assert atlas.content[8:12] == b"WEBP"


@pytest.mark.asyncio
async def test_root_referral_link_is_relative_to_the_app_origin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://ksuapi.example") as client:
        page = await client.get("/?startapp=ref_777")
    assert page.status_code == 200
    assert 'href="/mini-app/"' in page.text
    assert "URLSearchParams" in page.text
    assert "startapp" in page.text
    assert "https://t.me/" not in page.text
    assert urlsplit(str(page.url)).path == "/"
