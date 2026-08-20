from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"
DOC_ASSETS = ROOT / "docs" / "assets" / "roxy-promo"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _assert_png(path: Path) -> bytes:
    payload = path.read_bytes()
    assert len(payload) > 1_000_000
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    return payload


def test_supplied_promo_artworks_are_bundled_mounted_and_mirrored() -> None:
    partner = MINI / "roxy-partner-referrals-slide-source.png"
    creator = MINI / "roxy-creator-rewards-slide-source.png"
    brand = _read("roxy-brand.js")

    partner_payload = _assert_png(partner)
    creator_payload = _assert_png(creator)

    assert (DOC_ASSETS / "partner-referrals-runtime.png").read_bytes() == partner_payload
    assert (DOC_ASSETS / "creator-rewards-runtime.png").read_bytes() == creator_payload

    assert '/mini-app/roxy-partner-promo.css?v=12' in brand
    assert '/mini-app/roxy-partner-promo.js?v=12' in brand


def test_home_promo_carousel_uses_only_current_supplied_slides() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'id: "partner-referrals-35"' in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide-source.png?v=12"' in script
    assert 'id: "creator-rewards"' in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide-source.png?v=12"' in script
    assert 'roxy-partner-referrals-slide-source.webp?v=11' not in script
    assert 'roxy-creator-rewards-slide-source.webp?v=11' not in script
    assert 'roxy-partner-referrals-slide.webp?v=7' not in script
    assert 'roxy-creator-rewards-slide.webp?v=7' not in script
    assert "-hq.svg" not in script
    assert 'viewport.replaceChildren(...SLIDES.map(buildCard))' in script
    assert 'card.dataset.roxyFixedPromo = slide.id' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'console.error("[ROXY] Promo artwork failed to load"' in script
    assert 'card.classList.add("is-broken")' in script
    assert 'image.hidden = false' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_supplied_slides_render_compact_without_crop_or_visual_processing() -> None:
    css = _read("roxy-partner-promo.css")

    assert ".roxy-partner-promo-ready" in css
    assert ".roxy-promo-card.roxy-promo-artwork" in css
    assert "aspect-ratio: 16 / 9" in css
    assert "grid-auto-columns: min(56%, 460px) !important" in css
    assert "min-height: 0 !important" in css
    assert "object-fit: contain" in css
    assert "object-fit: cover" not in css
    assert "image-rendering: auto" in css
    assert "filter: none !important" in css
    assert "transform: none !important" in css
    assert ".roxy-promo-fallback" in css
