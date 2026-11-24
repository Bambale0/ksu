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
    assert '/login' in html
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


def test_hero_uses_approved_artwork_not_enlarged_sprite():
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert html.count('class="hero-line"') == 3
    assert '/site-assets/roxy-rx-transparent.png' in html
    photo_rule = css.split(".hero-art-photo{", 1)[1].split("}", 1)[0]
    assert "roxy-hero-cutout.webp" in photo_rule
    assert "background-size:contain" in photo_rule
    assert "atlas-" not in photo_rule
    for name in ("roxy-hero-cutout.webp", "roxy-official-mark.webp"):
        data = (ROOT / "assets" / name).read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert "--hero-x" in js and "--hero-y" in js
    assert "--asset-x" in js and "--spot-x" in js
    assert "resetHeroPointer" in js
    assert "feTurbulence" in css
    assert 'class="meta-tag"' in html


def test_floating_glass_navigation_and_alpha_logo_contract():
    html = HTML.read_text(encoding="utf-8")
    css = (ROOT / "assets/navbar.css").read_text(encoding="utf-8")
    js = (ROOT / "assets/navbar.js").read_text(encoding="utf-8")
    png = (ROOT / "assets/roxy-rx-transparent.png").read_bytes()
    assert png[:8] == bytes([137,80,78,71,13,10,26,10])
    assert png[25] == 6  # RGBA, not a black-backed RGB bitmap
    assert 'class="nav-slider"' in html
    assert html.index('<header class="site-header">') < html.index('id="reading-progress"') < html.index('</header>')
    assert 'mask: url("/site-assets/roxy-rx-transparent.png' in css
    assert "backdrop-filter: blur(" in css and "rx-contour-shine" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "aria-current" in js and "requestAnimationFrame" in js
    for filename in ("navbar.css","navbar.js"):
        data = (ROOT / "assets" / filename).read_bytes()
        fingerprint = sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()[:12]
        assert f"/site-assets/{filename}?v={fingerprint}" in html


def test_hero_cutout_has_real_transparency_and_soft_edges():
    from PIL import Image

    with Image.open(ROOT / "assets" / "roxy-hero-cutout.webp") as image:
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        histogram = alpha.histogram()
        assert histogram[0] > image.width * image.height * 0.1
        assert sum(histogram[1:250]) > image.width * image.height * 0.05
        assert sum(histogram[250:]) > image.width * image.height * 0.2
