"""Every tool and the browser entry has its own HTTP document."""
from hashlib import sha1
from pathlib import Path
import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1] / "app/web/site"
TOOLS = ("photo", "video", "text", "own-photo", "reference")
ROUTES = [(f"/features/{name}", f"feature-{name}") for name in TOOLS] + [("/login", "login"), ("/pricing", "pricing")]


@pytest.mark.asyncio
@pytest.mark.parametrize(("route", "identity"), ROUTES)
@pytest.mark.parametrize("suffix", ("", "/"))
async def test_independent_tool_or_login_document(route, identity, suffix):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get(route + suffix + "?ref=QA", follow_redirects=False)
        head = await client.head(route + suffix, follow_redirects=False)
    assert response.status_code == head.status_code == 200
    assert not head.content
    assert "location" not in response.headers and "location" not in head.headers
    assert "no-store" in response.headers["cache-control"]
    assert f'data-page="{identity}"' in response.text
    assert len(re.findall(r"<h1(?:\s|>)", response.text)) == 1
    assert f'rel="canonical" href="https://ksuapi.xn--e1aikcel5c5a.online{route}"' in response.text
    assert "/mini-app/_next/" not in response.text
    if identity == "login":
        assert 'name="robots" content="noindex,nofollow"' in response.text
        assert "site-login.js?v=" in response.text
    else:
        assert 'href="/login" data-app-link' in response.text


def test_home_cards_have_distinct_real_destinations_and_no_generic_app_links():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'class="format-card" href="([^"]+)"', html) == [
        f"/features/{name}" for name in TOOLS
    ]
    assert 'href="/mini-app/"' not in html
    assert 'href="/login" data-app-link' in html
    for route, identity in ROUTES:
        page = (ROOT / f"{identity}.html").read_text(encoding="utf-8")
        assert f'data-page="{identity}"' in page
        assert 'href="/mini-app/"' not in page


def test_login_and_cutout_asset_fingerprints_match():
    for asset, html in [
        ("site-login.js", "login.html"),
        ("roxy-hero-cutout.webp", "index.html"),
    ]:
        data = (ROOT / "assets" / asset).read_bytes()
        digest = sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()[:12]
        assert f"/site-assets/{asset}?v={digest}" in (ROOT / html).read_text(encoding="utf-8")
