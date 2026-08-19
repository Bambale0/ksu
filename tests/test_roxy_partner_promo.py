from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _assert_4k_webp(path: Path, minimum_size: int) -> bytes:
    payload = path.read_bytes()
    assert len(payload) > minimum_size
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"
    return payload


def test_4k_promo_artworks_are_bundled_and_mounted() -> None:
    partner = MINI / "roxy-partner-referrals-slide-4k.webp"
    creator = MINI / "roxy-creator-rewards-slide-4k.webp"
    brand = _read("roxy-brand.js")

    assert partner.is_file()
    _assert_4k_webp(partner, 250_000)
    assert creator.is_file()
    _assert_4k_webp(creator, 400_000)

    assert '/mini-app/roxy-partner-promo.css?v=8' in brand
    assert '/mini-app/roxy-partner-promo.js?v=8' in brand


def test_home_promo_carousel_uses_only_4k_raster_slides() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'id: "partner-referrals-35"' in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide-4k.webp?v=8"' in script
    assert 'id: "creator-rewards"' in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide-4k.webp?v=8"' in script
    assert "-hq.svg" not in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide.webp' not in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide.webp' not in script
    assert 'viewport.replaceChildren(...SLIDES.map(buildCard))' in script
    assert 'card.dataset.roxyFixedPromo = slide.id' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'console.error("[ROXY] Promo artwork failed to load"' in script
    assert 'card.classList.add("is-broken")' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_4k_slides_keep_artwork_crisp_in_compact_carousel() -> None:
    css = _read("roxy-partner-promo.css")

    assert ".roxy-partner-promo-ready" in css
    assert ".roxy-promo-card.roxy-promo-artwork" in css
    assert "aspect-ratio: 16 / 9" in css
    assert "min-height: clamp(168px, 45vw, 220px) !important" in css
    assert "object-fit: cover" in css
    assert "image-rendering: auto" in css
    assert "filter: none !important" in css
    assert "transform: none !important" in css
    assert ".roxy-promo-fallback" in css
