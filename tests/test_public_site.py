"""Marketing domain root is a standalone static site, independent from Mini App."""
import importlib
from hashlib import sha1
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
    assert "ROXY AI STUDIO" in html.text
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


def test_editorial_site_contract_and_independent_branding() -> None:
    """Prevent a return to repeated, noninteractive cards and broken tablet navigation."""
    root = ROOT / "app/web/site"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "assets/styles.css").read_text(encoding="utf-8")

    assert "<title>ROXY AI STUDIO" in html
    assert 'class="logo-wordmark"' in html
    assert html.count('class="capability"') == 4
    assert html.count('class="process-row"') == 3
    assert 'id="popular-trends"' in html
    assert 'id="popular-trends-status"' in html
    assert 'src="/site-assets/popular-trends.js?v=' in html
    assert 'class="gallery-item ' not in html
    assert 'class="capabilities-stage"' in html
    assert 'class="editorial-intro"' in html
    assert 'class="gallery-outro"' in html
    assert "feature-card" not in html
    assert "feature-icon" not in html
    assert "gallery-tags" not in html
    assert "Миллион версий" not in html
    assert 'data-app-link' in html
    assert "/mini-app/_next/" not in html
    assert "ROXY AI STUDIO" in html
    assert "/site-assets/" in css
    assert ".gallery-item:nth-child(6){grid-column:span 6;grid-row:span 2}" in css
    assert "grid-column:span 12" not in css
    assert ".live-trend-media" in css
    assert "  .gallery-item:nth-child(6){grid-column:span 2;grid-row:span 1}" in css
    assert ".mobile-nav{display:block" in css
    assert "@media(max-width:1000px)" in css
    assert "@media(max-width:660px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_live_trend_gallery_is_public_and_never_hardcodes_popular_items() -> None:
    root = ROOT / "app/web/site"
    html = (root / "index.html").read_text(encoding="utf-8")
    javascript = (root / "assets/popular-trends.js").read_text(encoding="utf-8")
    assert 'id="popular-trends"' in html
    assert "gallery-portrait" not in html
    assert "class=\"gallery-item " not in html
    assert "/api/v1/public-site/popular-trends?limit=6" in javascript
    assert 'new IntersectionObserver' in javascript
    assert 'video.muted = true;' in javascript
    assert 'video.playsInline = true;' in javascript
    assert 'video.loop = true;' in javascript
    assert "reducedMotion.matches" in javascript
    assert "saveData" in javascript
    assert 'textContent = title' in javascript
    assert 'link.href = openTrendUrl(item.id)' in javascript
    assert 'credentials: "omit"' in javascript
    assert 'cache: "default"' in javascript
    assert 'gallery.replaceChildren(...tiles)' in javascript


def test_public_editorial_polish_preserves_usable_real_content() -> None:
    """Regression guard for screenshot bugs and non-actionable affordances."""
    root = ROOT / "app/web/site"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "assets/styles.css").read_text(encoding="utf-8")

    assert '<h2 id="gallery-title">Что повторяют чаще всего.</h2>' in html
    assert 'id="popular-trends"' in html
    assert "Не ищи шаблон." not in html
    assert "Миллион версий" not in html
    assert "capability-mark" not in html
    assert "capability-index" not in html
    assert "process-symbol" not in html
    assert 'Можно ли работать без опыта?' in html
    assert 'Да. Достаточно описать идею' in html
    assert 'Нет. Достаточно идеи' not in html

    # Six images should be balanced, not a full-bleed 1200px-wide sixth tile.
    assert ".gallery-item:nth-child(6){grid-column:span 6;grid-row:span 2}" in css
    assert "  .gallery-item:nth-child(6){grid-column:span 2;grid-row:span 1}" in css
    assert "grid-column:span 12" not in css
    assert "scroll-padding-top:100px" in css
    assert "scroll-padding-top:84px" in css
    assert "scroll-margin-top:" not in css
    assert "max-width:1000px" in css
    assert "min-width:661px" in css
    assert "max-width:660px" in css
    assert "prefers-reduced-motion:reduce" in css

    # Use the standalone site and real data. No shadcn React dependency/bundle.
    assert "/site-assets/popular-trends.js" in html
    assert "/mini-app/_next/" not in html
    assert "radix-ui" not in html
    assert "react" not in html.lower()

def test_capabilities_composition_keeps_atlas_aspect_ratio_and_clean_overlay() -> None:
    """Prevent portrait stretching and over-decorated features composition."""
    root = ROOT / "app/web/site"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "assets/styles.css").read_text(encoding="utf-8")

    # The atlas is a 3x3 sprite: preserve the source aspect ratio and crop
    # horizontally rather than stretching portrait cells into tall rectangles.
    assert ".stage-frame{position:absolute;" in css
    assert "background-size:auto 300%" in css
    assert ".stage-frame-main{inset:0;background-position:12% 0%}" in css
    assert ".capabilities-stage{position:relative;isolation:isolate;aspect-ratio:1/1;" in css
    assert ".capabilities-stage{min-height:0;aspect-ratio:4/5;" in css
    assert "font-size:clamp(42px,5.25vw,74px)" not in css

    # Make the photographic work itself the focus, not simulated portfolio chrome.
    assert "ROXY<br>STUDIES" not in html
    assert "Демонстрационные образы" not in html


def test_public_site_asset_urls_follow_actual_content_fingerprints() -> None:
    """HTML must use a fresh asset URL when CSS or JS bytes change.

    HTML itself is no-store, but browser/CDN caches may retain an unchanged
    /site-assets/styles.css or popular-trends.js URL after production deploy.
    """

    root = ROOT / "app/web/site"
    html = (root / "index.html").read_text(encoding="utf-8")
    for filename, tag in (
        ("styles.css", "href"),
        ("popular-trends.js", "src"),
    ):
        payload = (root / "assets" / filename).read_bytes()
        git_blob = b"blob " + str(len(payload)).encode("ascii") + bytes([0]) + payload
        version = sha1(git_blob).hexdigest()[:12]
        assert f'{tag}="/site-assets/{filename}?v={version}"' in html
