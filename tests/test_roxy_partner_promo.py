from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _assert_webp(path: Path, expected_sha256: str) -> bytes:
    payload = path.read_bytes()
    assert len(payload) > 1_000_000
    assert payload.startswith(b"RIFF")
    assert payload[8:12] == b"WEBP"
    assert sha256(payload).hexdigest() == expected_sha256
    return payload


def test_supplied_promo_artworks_are_bundled_and_mounted() -> None:
    partner = MINI / "roxy-partner-referrals-slide-source.webp"
    creator = MINI / "roxy-creator-rewards-slide-source.webp"
    brand = _read("roxy-brand.js")

    assert partner.is_file()
    _assert_webp(partner, "0001f8c4c4a28d9fb5f05ee6d84e367fdcd25e11d097a1291cd9461dacd5ca7d")
    assert creator.is_file()
    _assert_webp(creator, "63d0cd08b5ae563f13521e349f694e8df444a2f168364b560d7a1f69838462d5")

    assert '/mini-app/roxy-partner-promo.css?v=9' in brand
    assert '/mini-app/roxy-partner-promo.js?v=9' in brand


def test_home_promo_carousel_uses_only_current_supplied_slides() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'id: "partner-referrals-35"' in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide-source.webp?v=9"' in script
    assert 'id: "creator-rewards"' in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide-source.webp?v=9"' in script
    assert 'roxy-partner-referrals-slide.webp?v=7' not in script
    assert 'roxy-creator-rewards-slide.webp?v=7' not in script
    assert "-hq.svg" not in script
    assert 'viewport.replaceChildren(...SLIDES.map(buildCard))' in script
    assert 'card.dataset.roxyFixedPromo = slide.id' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'console.error("[ROXY] Promo artwork failed to load"' in script
    assert 'card.classList.add("is-broken")' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_supplied_slides_render_without_crop_or_visual_processing() -> None:
    css = _read("roxy-partner-promo.css")

    assert ".roxy-partner-promo-ready" in css
    assert ".roxy-promo-card.roxy-promo-artwork" in css
    assert "aspect-ratio: 16 / 9" in css
    assert "min-height: clamp(168px, 45vw, 220px) !important" in css
    assert "object-fit: contain" in css
    assert "object-fit: cover" not in css
    assert "image-rendering: auto" in css
    assert "filter: none !important" in css
    assert "transform: none !important" in css
    assert ".roxy-promo-fallback" in css
