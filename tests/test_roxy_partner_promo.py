from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _assert_jpeg(path: Path) -> None:
    payload = path.read_bytes()
    assert len(payload) > 3_000
    assert payload.startswith(b"\xff\xd8")
    assert payload.endswith(b"\xff\xd9")


def _assert_webp(path: Path) -> None:
    payload = path.read_bytes()
    assert len(payload) > 8_000
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"


def test_supplied_promo_artworks_are_bundled_and_mounted() -> None:
    partner = MINI / "roxy-partner-referrals-slide.jpg"
    creator = MINI / "roxy-creator-rewards-slide.webp"
    brand = _read("roxy-brand.js")

    assert partner.is_file()
    _assert_jpeg(partner)
    assert creator.is_file()
    _assert_webp(creator)
    assert '/mini-app/roxy-partner-promo.css' in brand
    assert '/mini-app/roxy-partner-promo.js' in brand


def test_home_promo_carousel_is_replaced_with_only_supplied_slides() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'id: "partner-referrals-35"' in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide.jpg"' in script
    assert 'id: "creator-rewards"' in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide.webp"' in script
    assert 'viewport.replaceChildren(...SLIDES.map(buildCard))' in script
    assert 'data-roxy-fixed-promo' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_supplied_slides_keep_artwork_readable_in_compact_carousel() -> None:
    css = _read("roxy-partner-promo.css")

    assert ".roxy-partner-promo-ready" in css
    assert ".roxy-promo-card.roxy-promo-artwork" in css
    assert "aspect-ratio: 2048 / 1142" in css
    assert "min-height: clamp(168px, 45vw, 220px) !important" in css
    assert "object-fit: cover" in css
    assert "#0B0B10" in css
    assert "#9B5CFF" in css
