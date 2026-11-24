"""The public website owns an explicit, independent multipage surface."""
from pathlib import Path
import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1] / "app/web/site"
PAGES = ("features", "gallery", "process", "faq")


@pytest.mark.asyncio
@pytest.mark.parametrize("page", PAGES)
async def test_public_page_has_real_get_head_and_unique_metadata(page):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/{page}?ref=QA", follow_redirects=False)
        head = await client.head(f"/{page}", follow_redirects=False)
    assert response.status_code == head.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]
    assert not head.content
    assert f'data-page="{page}"' in response.text
    assert f'href="/{page}" data-site-link aria-current="page"' in response.text
    assert len(re.findall(r"<h1(?:\s|>)", response.text)) == 1
    assert f'rel="canonical" href="https://ksuapi.xn--e1aikcel5c5a.online/{page}"' in response.text
    assert "mini-app/_next/" not in response.text


@pytest.mark.asyncio
async def test_unknown_public_path_does_not_fall_through_to_home():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/nonexistent-public-page", "/landing", "/features/unknown"):
            assert (await client.get(path, follow_redirects=False)).status_code == 404


def test_all_pages_share_navigation_and_assets_but_have_distinct_titles():
    titles = set()
    for page in ("index", *PAGES):
        html = (ROOT / f"{page}.html").read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        assert title not in titles
        titles.add(title)
        for link in ("/", *[f"/{p}" for p in PAGES]):
            assert f'href="{link}" data-site-link' in html
        assert html.count('class="site-header"') == 1
        assert html.count('class="site-footer"') == 1
        assert '/site-assets/experience.css?v=' in html
        assert '/site-assets/navbar.js?v=' in html
    assert 'data-limit="12"' in (ROOT / "gallery.html").read_text(encoding="utf-8")
