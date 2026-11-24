"""Public ROXY creative landing: visual direction and motion acceptance contracts."""
from hashlib import sha1
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app/web/site"
HTML = ROOT / "index.html"
CSS = ROOT / "assets/experience.css"
JS = ROOT / "assets/experience.js"


def test_new_hero_replaces_tile_mosaic_and_keeps_real_ctas():
    html = HTML.read_text(encoding="utf-8")
    assert 'class="hero-art"' in html
    assert 'class="hero-mosaic"' not in html
    assert 'class="chrome-letter"' not in html
    assert 'class="hero-copy"' in html
    assert 'class="hero-formats"' in html
    assert html.count('class="format-card"') == 5
    assert 'class="brand-monogram"' in html
    assert 'id="popular-trends"' in html
    assert '/mini-app/' in html
    assert 'data-app-link' in html


def test_reading_progress_and_morphing_path_have_accessible_markup():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="reading-progress"' in html
    assert 'role="progressbar"' in html
    assert 'aria-valuemin="0"' in html and 'aria-valuemax="100"' in html
    assert 'id="scroll-trace-path"' in html
    assert 'viewBox=' in html


def test_motion_uses_one_raf_schedule_and_respects_reduced_motion():
    script = JS.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "requestAnimationFrame" in script
    assert "passive: true" in script
    assert "prefers-reduced-motion: reduce" in script
    assert "pointermove" in script and "pointerout" in script
    assert "getTotalLength" in script and "strokeDashoffset" in script
    assert "setAttribute(\"aria-valuenow\"" in script
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (hover: hover) and (pointer: fine)" in css
    assert "translate3d" in css and "rotateX" in css
    assert "overflow-x: hidden" not in css  # fix layout, do not mask overflow


def test_new_asset_versions_track_git_blob_hashes():
    html = HTML.read_text(encoding="utf-8")
    for file in (CSS, JS):
        data = file.read_bytes()
        blob = b"blob " + str(len(data)).encode() + b"\0" + data
        fingerprint = sha1(blob).hexdigest()[:12]
        assert f'/site-assets/{file.name}?v={fingerprint}' in html

def test_rx_branded_social_preview_is_present_and_has_explicit_dimensions():
    html = HTML.read_text(encoding="utf-8")
    assert '/site-assets/roxy-mark.svg' in html
    assert 'property="og:image"' in html
    assert 'roxy-social-preview.png?v=' in html
    assert 'property="og:image:width" content="1200"' in html
    assert 'property="og:image:height" content="630"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    preview = (ROOT / "assets" / "roxy-social-preview.png").read_bytes()
    assert preview[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    assert int.from_bytes(preview[16:20], "big") == 1200
    assert int.from_bytes(preview[20:24], "big") == 630
