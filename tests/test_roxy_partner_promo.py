from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _assert_hq_svg(path: Path) -> str:
    payload = path.read_text(encoding="utf-8")
    assert payload.lstrip().startswith("<svg")
    assert 'width="2048"' in payload
    assert 'height="1152"' in payload
    assert 'viewBox="0 0 2048 1152"' in payload
    assert "#0B0B10" in payload
    assert "#9B5CFF" in payload
    assert "#FF5FB7" in payload
    return payload


def test_hq_promo_artworks_are_vector_bundled_and_mounted() -> None:
    partner = MINI / "roxy-partner-referrals-slide-hq.svg"
    creator = MINI / "roxy-creator-rewards-slide-hq.svg"
    brand = _read("roxy-brand.js")

    assert partner.is_file()
    partner_svg = _assert_hq_svg(partner)
    assert "35%" in partner_svg
    assert "с пополнений рефералов" in partner_svg

    assert creator.is_file()
    creator_svg = _assert_hq_svg(creator)
    assert "СОЗДАВАЙ." in creator_svg
    assert "ПУБЛИКУЙ." in creator_svg
    assert "ЗАРАБАТЫВАЙ." in creator_svg

    assert '/mini-app/roxy-partner-promo.css?v=6' in brand
    assert '/mini-app/roxy-partner-promo.js?v=6' in brand


def test_home_promo_carousel_uses_only_hq_vector_slides() -> None:
    script = _read("roxy-partner-promo.js")

    assert 'id: "partner-referrals-35"' in script
    assert 'image: "/mini-app/roxy-partner-referrals-slide-hq.svg?v=6"' in script
    assert 'id: "creator-rewards"' in script
    assert 'image: "/mini-app/roxy-creator-rewards-slide-hq.svg?v=6"' in script
    assert 'viewport.replaceChildren(...SLIDES.map(buildCard))' in script
    assert 'card.dataset.roxyFixedPromo = slide.id' in script
    assert 'observer.observe(viewport, { childList: true })' in script
    assert 'console.error("[ROXY] Promo artwork failed to load"' in script
    assert 'card.classList.add("is-broken")' in script
    assert 'document.body' not in script.split("MutationObserver", 1)[-1]


def test_hq_slides_keep_artwork_crisp_in_compact_carousel() -> None:
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
    assert "#0B0B10" in css
    assert "#9B5CFF" in css
