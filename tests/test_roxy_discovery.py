from pathlib import Path

from app.services.discovery import DiscoveryService


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_discovery_service_normalizes_admin_promo_payload_safely() -> None:
    slides = DiscoveryService.normalize_slides(
        {
            "slides": [
                {
                    "id": "partner",
                    "eyebrow": "Creators",
                    "title": "Партнёрская программа",
                    "body": "Индивидуальные условия",
                    "cta": "Узнать",
                    "action": {"type": "route", "target": "profile"},
                    "image_url": "https://cdn.example/banner.webp",
                },
                {
                    "title": "Bad target falls back",
                    "action": {"type": "route", "target": "admin"},
                    "image_url": "javascript:alert(1)",
                },
                {"title": "Trends", "action": {"type": "trends"}},
                {"body": "missing title"},
            ]
        }
    )
    assert len(slides) == 3
    assert slides[0]["action"] == {"type": "route", "target": "profile"}
    assert slides[0]["image_url"] == "https://cdn.example/banner.webp"
    assert slides[1]["action"] == {"type": "route", "target": "catalog"}
    assert slides[1]["image_url"] is None
    assert slides[2]["action"] == {"type": "trends", "target": "trends"}


def test_discovery_defaults_cover_customer_feedback() -> None:
    titles = {str(item["title"]) for item in DiscoveryService.DEFAULT_SLIDES}
    assert "Партнёрская программа" in titles
    assert "Создавай фото и видео" in titles
    assert "Шаблоны, тренды и работы сообщества" in titles
    assert DiscoveryService.HOME_PROMOS_SLUG == "roxy-home-promos"


def test_discovery_api_is_registered_and_authenticated() -> None:
    router = _read("app/api/router.py")
    api = _read("app/api/v1/discovery.py")
    assert "discovery," in router
    assert "api_router.include_router(discovery.router)" in router
    assert 'APIRouter(prefix="/discovery"' in api
    assert '@router.get("/home")' in api
    assert "CurrentUserDep" in api
    assert "DiscoveryService.home(session)" in api


def test_mini_app_catalog_is_real_discovery_surface_not_feed_rename() -> None:
    discovery = _read("app/web/mini_app/roxy-discovery.js")
    navigation = _read("app/web/mini_app/roxy-customer-navigation.js")
    brand = _read("app/web/mini_app/roxy-brand.js")
    css = _read("app/web/mini_app/roxy-discovery.css")

    assert 'api("/api/v1/discovery/home")' in discovery
    assert 'api("/api/v1/trends?limit=8")' in discovery
    assert 'api("/api/v1/feed?sort=top_day&limit=6")' in discovery
    assert "Шаблоны и тренды" in discovery
    assert "Лента сообщества" in discovery
    assert "Фото и видео пользователей" in discovery
    assert "openCommunityFeed" in discovery
    assert "RoxyDiscovery" in navigation
    assert 'classList.contains("roxy-discovery-catalog-open")' in navigation
    assert '/mini-app/roxy-discovery.js' in brand
    assert '/mini-app/roxy-discovery.css' in brand
    assert ".roxy-promo-viewport" in css
    assert ".roxy-catalog-view" in css
    assert "scroll-snap-type: x mandatory" in css


def test_home_promos_are_server_driven_not_business_copy_in_browser() -> None:
    discovery_js = (MINI / "roxy-discovery.js").read_text(encoding="utf-8")
    assert "Партнёрская программа" not in discovery_js
    assert "ежемесячные ROX" not in discovery_js
    assert 'state.home = await api("/api/v1/discovery/home")' in discovery_js
