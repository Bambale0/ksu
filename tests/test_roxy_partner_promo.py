from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_supplied_partner_artwork_is_bundled_and_mounted() -> None:
    asset = MINI / "roxy-partner-referrals-slide.jpg"
    brand = _read("roxy-brand.js")

    assert asset.is_file()
    assert asset.stat().st_size > 10_000
    assert '/mini-app/roxy-partner-promo.css' in brand
    assert '/mini-app/roxy-partner-promo.js' in brand


def test_partner_artwork_is_always_inserted_as_second_home_promo() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'const PROMO_ID = "partner-referrals-35"' in script
    assert 'const PROMO_IMAGE = "/mini-app/roxy-partner-referrals-slide.jpg"' in script
    assert 'first.insertAdjacentElement("afterend", fixed)' in script
    assert 'data-roxy-fixed-promo' in script
    assert 'window.RoxyCustomerNavigation.open("profile")' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_partner_slide_keeps_artwork_readable_in_compact_carousel() -> None:
    css = _read("roxy-partner-promo.css")

    assert ".roxy-partner-promo-ready" in css
    assert ".roxy-promo-card.roxy-promo-artwork" in css
    assert "aspect-ratio: 2048 / 1142" in css
    assert "min-height: clamp(168px, 45vw, 220px) !important" in css
    assert "object-fit: cover" in css
    assert "#0B0B10" in css
    assert "#9B5CFF" in css
